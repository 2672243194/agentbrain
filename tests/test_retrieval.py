from agentbrain.retrieval import tokenize


def test_tokenize_mixed_language():
    toks = tokenize("Fix 证据链 issue 证据链管理")
    assert "fix" in toks and "issue" in toks
    assert toks.count("证据") >= 2
    assert "证据链" not in toks  # CJK is indexed as bigrams


def test_tokenize_single_cjk_char():
    assert tokenize("图") == ["图"]


def test_search_ranks_relevant_first(vault):
    from agentbrain import api

    api.memory_ingest(
        case_id="c-db",
        lesson="Always use retry with exponential backoff for Postgres connections",
        tags=["db"],
        source_summary="Postgres retry pattern",
        vault=vault,
    )
    api.memory_ingest(
        case_id="c-ui",
        lesson="Handle retry on form submit to avoid duplicate posts",
        tags=["ui"],
        source_summary="UI loading states",
        vault=vault,
    )
    out = api.memory_query(query="postgres retry", top_k=2, vault=vault)
    assert "c-db-lesson-01" in out
    assert out.index("c-db-lesson-01") < out.index("c-ui-lesson-01")


def test_search_chinese(vault):
    from agentbrain import api

    api.memory_ingest(
        case_id="c-evidence",
        lesson="证据链必须当天固定，隔天取证可信度下降",
        tags=["证据"],
        source_summary="证据链当天固定",
        vault=vault,
    )
    out = api.memory_query(query="证据链 固定", top_k=3, vault=vault)
    assert "c-evidence-lesson-01" in out
