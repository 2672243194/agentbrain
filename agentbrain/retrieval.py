from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, datetime

from .models import Lesson

_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+")


def tokenize(text: str) -> list[str]:
    tokens = [w.lower() for w in _WORD.findall(text or "")]
    for run in _CJK_RUN.findall(text or ""):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


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


def _doc_tokens(lesson: Lesson) -> list[str]:
    tag_tokens: list[str] = []
    for tag in lesson.tags:
        tag_tokens.extend(tokenize(tag))
    return (
        tokenize(lesson.source_summary) * 3
        + tag_tokens * 2
        + tokenize(lesson.case_id)
        + tokenize(lesson.content)
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
    if not lessons:
        return []
    q = tokenize(query)
    if not q:
        return []
    bm25 = BM25([_doc_tokens(l) for l in lessons])
    scored: list[tuple[Lesson, float]] = []
    for i, lesson in enumerate(lessons):
        s = bm25.score(q, i)
        if s <= 0:
            continue
        scored.append((lesson, s * _boost(lesson)))
    scored.sort(key=lambda x: (-x[1], x[0].lesson_id))
    return scored
