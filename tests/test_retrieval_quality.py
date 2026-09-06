"""Regression cases for useful, current and intent-preserving retrieval."""

from datetime import date, timedelta

import pytest

from agentbrain.models import Lesson
from agentbrain.retrieval import search_lessons, tokenize


@pytest.mark.parametrize(
    ("summary", "query"),
    [
        ("memory_query", "memory query"),
        ("memory query", "memory_query"),
        ("readLesson", "read lesson"),
        ("read lesson", "readLesson"),
        ("HTTPClient", "http client"),
        ("http client", "HTTPClient"),
    ],
)
def test_identifier_and_natural_words_retrieve_each_other(summary, query):
    lesson = Lesson("target", "case", summary)
    assert [hit.lesson_id for hit, _ in search_lessons([lesson], query)] == ["target"]


def test_identifiers_keep_exact_form_for_precise_search():
    tokens = tokenize("memory_query HTTPClient")
    assert "memory_query" in tokens
    assert "httpclient" in tokens


def test_repeating_query_terms_does_not_change_scores_or_ranking():
    lessons = [
        Lesson("database", "case", "postgres retry"),
        Lesson("ui", "case", "retry retry retry form submit"),
    ]
    once = search_lessons(lessons, "postgres retry")
    repeated = search_lessons(lessons, "postgres retry retry retry")
    assert [(hit.lesson_id, score) for hit, score in repeated] == [
        (hit.lesson_id, score) for hit, score in once
    ]


def test_popularity_does_not_displace_complete_relevant_match():
    lessons = [
        Lesson("specific", "case", "Postgres connection retries"),
        Lesson("popular", "case", "Postgres connection", use_count=25),
        Lesson("other", "case", "UI retries"),
    ]
    ranked = search_lessons(lessons, "Postgres connection retries")
    assert ranked[0][0].lesson_id == "specific"


def test_recorded_use_still_helps_equally_relevant_lessons():
    lessons = [
        Lesson("never-read", "case", "Postgres connection retries"),
        Lesson("used", "case", "Postgres connection retries", use_count=5),
    ]
    assert search_lessons(lessons, "Postgres connection retries")[0][0].lesson_id == "used"


@pytest.mark.parametrize("days_from_today", [-1, 0])
def test_expired_lessons_are_not_recommended(days_from_today):
    lesson = Lesson(
        "expired", "case", "python module",
        valid_until=(date.today() + timedelta(days=days_from_today)).isoformat(),
    )
    assert search_lessons([lesson], "python") == []


@pytest.mark.parametrize("valid_until", ["", "bad-date", "2999-01-01"])
def test_unknown_or_future_expiry_does_not_hide_lessons(valid_until):
    lesson = Lesson("current", "case", "python module", valid_until=valid_until)
    assert search_lessons([lesson], "python")[0][0].lesson_id == "current"


def test_superseded_lessons_are_not_recommended():
    retired = Lesson("retired", "case", "python module", superseded_by="replacement")
    assert search_lessons([retired], "python") == []


def test_single_cjk_query_retrieves_character_inside_phrase():
    lesson = Lesson("image", "case", "图片压缩")
    assert search_lessons([lesson], "图")[0][0].lesson_id == "image"


def test_multichar_cjk_query_keeps_bigram_precision():
    lessons = [
        Lesson("image", "case", "图片压缩"),
        Lesson("map", "case", "地图缩放"),
    ]
    assert [hit.lesson_id for hit, _ in search_lessons(lessons, "图片")] == ["image"]


def test_excluded_lessons_do_not_affect_active_scores():
    current = Lesson("current", "case", "python module")
    retired = Lesson("retired", "case", "python python python", superseded_by="current")
    assert search_lessons([current, retired], "python") == search_lessons([current], "python")


@pytest.fixture
def token_cache():
    from agentbrain import retrieval

    retrieval._cached_tokens.cache_clear()
    yield retrieval
    retrieval._cached_tokens.cache_clear()


def test_token_cache_returns_independent_lists(token_cache):
    original = tokenize("memory_query 图片压缩")
    altered = tokenize("memory_query 图片压缩")
    altered.clear()
    altered.append("injected")
    assert tokenize("memory_query 图片压缩") == original


def test_token_cache_reuses_document_text_across_distinct_queries(token_cache, monkeypatch):
    parsed: list[str] = []
    original = token_cache._tokenize_uncached

    def record(text):
        parsed.append(text)
        return original(text)

    monkeypatch.setattr(token_cache, "_tokenize_uncached", record)
    lesson = Lesson("same", "case", "database guidance", "postgres connections retry safely")
    assert search_lessons([lesson], "postgres")
    parsed.clear()
    assert search_lessons([lesson], "retry")
    assert parsed == ["retry"]


def test_token_cache_updates_immediately_when_same_lesson_content_changes(token_cache):
    lesson = Lesson("same", "case", "database guidance", "postgres connections")
    assert search_lessons([lesson], "postgres")
    lesson.content = "sqlite connections"
    assert search_lessons([lesson], "postgres") == []
    assert search_lessons([lesson], "sqlite")[0][0].lesson_id == "same"
    lesson.valid_until = date.today().isoformat()
    assert search_lessons([lesson], "sqlite") == []


def test_oversized_text_bypasses_token_cache(token_cache):
    text = "retry " * (token_cache._TOKEN_CACHE_MAX_CHARS // 6 + 1)
    assert tokenize(text) == text.split()
    assert token_cache._cached_tokens.cache_info().currsize == 0


def test_token_cache_has_finite_entry_limit(token_cache):
    for index in range(token_cache._TOKEN_CACHE_SIZE + 10):
        tokenize(f"unique_cache_entry_{index}")
    assert token_cache._cached_tokens.cache_info().currsize == token_cache._TOKEN_CACHE_SIZE
