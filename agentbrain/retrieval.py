from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime
from functools import lru_cache

from .models import Lesson

_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")
_IDENTIFIER_BOUNDARY = re.compile(
    r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)
_TOKEN_CACHE_SIZE = 256
_TOKEN_CACHE_MAX_CHARS = 2048


def _tokenize_uncached(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD.findall(text or ""):
        normalized = word.lower()
        tokens.append(normalized)
        if "_" in word or not word.islower():
            parts = [part.lower() for part in _IDENTIFIER_BOUNDARY.split(word) if part]
            if parts != [normalized]:
                tokens.extend(parts)
    for run in _CJK_RUN.findall(text or ""):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


@lru_cache(maxsize=_TOKEN_CACHE_SIZE)
def _cached_tokens(text: str) -> tuple[str, ...]:
    return tuple(_tokenize_uncached(text))


def tokenize(text: str) -> list[str]:
    """Reuse bounded text-only tokenization; callers always own their list."""
    text = text or ""
    if len(text) > _TOKEN_CACHE_MAX_CHARS:
        return _tokenize_uncached(text)
    return list(_cached_tokens(text))


def oneline(text: str, n: int) -> str:
    """Collapse whitespace and truncate to n characters (ellipsis-terminated)."""
    s = " ".join((text or "").split())
    return s[: n - 1] + "…" if len(s) > n else s


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        n = len(docs)
        self.doc_len = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_len) / n) if n else 0.0
        self.tfs = [Counter(d) for d in docs]
        df: Counter[str] = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def score(self, q_tokens: list[str], i: int) -> float:
        tf = self.tfs[i]
        dl = self.doc_len[i] or 1
        s = 0.0
        for t in q_tokens:
            f = tf.get(t, 0)
            if not f:
                continue
            idf = self.idf.get(t, 0.0)
            s += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
        return s


def _doc_tokens(lesson: Lesson, single_cjk: set[str] | None = None) -> list[str]:
    def field_tokens(text: str) -> list[str]:
        tokens = tokenize(text)
        if single_cjk:
            # Only index individual characters explicitly requested by this
            # query. Ordinary CJK queries retain bigram precision.
            for run in _CJK_RUN.findall(text or ""):
                if len(run) > 1:
                    tokens.extend(char for char in run if char in single_cjk)
        return tokens

    tag_tokens: list[str] = []
    for tag in lesson.tags:
        tag_tokens.extend(field_tokens(tag))
    return (
        field_tokens(lesson.source_summary) * 3
        + tag_tokens * 2
        + field_tokens(lesson.case_id)
        + field_tokens(lesson.content)
    )


def _days_since(iso: str) -> int | None:
    if not iso:
        return None
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (date.today() - d).days


def _boost(lesson: Lesson) -> float:
    b = 1.0
    if lesson.verified:
        b *= 1.10
    b *= 1 + 0.02 * min(lesson.use_count, 25)
    d = _days_since(lesson.last_verified_at)
    if d is not None:
        if d <= 30:
            b *= 1.15
        elif d > 365:
            b *= 0.85
    return b


def search_lessons(lessons: list[Lesson], query: str) -> list[tuple[Lesson, float]]:
    q = list(dict.fromkeys(tokenize(query)))
    if not q:
        return []
    active: list[Lesson] = []
    for lesson in lessons:
        expired_days = _days_since(lesson.valid_until)
        if not lesson.superseded_by and (expired_days is None or expired_days < 0):
            active.append(lesson)
    if not active:
        return []
    single_cjk = {token for token in q if len(token) == 1 and _CJK_RUN.fullmatch(token)}
    bm25 = BM25([_doc_tokens(lesson, single_cjk) for lesson in active])
    scored: list[tuple[Lesson, float]] = []
    for i, lesson in enumerate(active):
        s = bm25.score(q, i)
        if s <= 0:
            continue
        # Reward covering the task's distinct keywords so popular partial
        # matches cannot rely on their read history alone to rank highly.
        coverage = sum(token in bm25.tfs[i] for token in q) / len(q)
        scored.append((lesson, s * coverage * _boost(lesson)))
    scored.sort(key=lambda x: (-x[1], x[0].lesson_id))
    return scored
