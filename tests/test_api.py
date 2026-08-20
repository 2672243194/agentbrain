from agentbrain import api


def test_query_empty_result_hint(vault):
    out = api.memory_query("zzzunmatchedqueryxyz", vault=vault)
    assert "No lessons matched" in out


def test_ingest_and_query_flow(vault):
    out = api.memory_ingest(
        case_id="case-001",
        lesson="部署前必须先跑数据库迁移脚本",
        tags=["部署", "运维"],
        vault=vault,
    )
    assert "Saved case-001-lesson-01" in out

    out = api.memory_query("部署 迁移", vault=vault)
    assert "case-001-lesson-01" in out

    lesson = vault.get("case-001-lesson-01")
    assert lesson.use_count == 1


def test_ingest_refuses_empty_lesson(vault):
    assert "Refused" in api.memory_ingest(case_id="c", lesson="  ", vault=vault)


def test_ingest_normalizes_tags_and_case(vault):
    out = api.memory_ingest(case_id="My Case/1", lesson="内容", tags="a, a,, b", vault=vault)
    assert "My-Case-1-lesson-01" in out
    lesson = vault.get("My-Case-1-lesson-01")
    assert lesson.tags == ["a", "b"]


def test_lint_detects_duplicates(vault):
    api.memory_ingest(case_id="c1", lesson="always pin dependencies in requirements.txt", tags=["deps"], source_summary="pin dependencies", vault=vault)
    api.memory_ingest(case_id="c2", lesson="always pin your dependencies in the requirements file", tags=["deps"], source_summary="pin dependencies exactly", vault=vault)
    out = api.memory_lint(vault=vault)
    assert "DUPLICATE" in out
    assert any(p.name.startswith("lint-") for p in vault.consolidations_dir.glob("*.md"))


def test_lint_clean_vault(vault):
    out = api.memory_lint(vault=vault)
    assert "clean" in out.lower()


def test_lint_scope_tag(vault):
    api.memory_ingest(case_id="c1", lesson="content about database indexes", tags=["db"], confidence=0.3, vault=vault)
    api.memory_ingest(case_id="c2", lesson="content about css flexbox layout", tags=["ui"], confidence=0.3, vault=vault)
    out = api.memory_lint(scope="tag:ui", vault=vault)
    assert "c2-lesson-01" in out
    assert "c1-lesson-01" not in out


def test_distill_no_pattern(vault):
    out = api.memory_distill(window_days=30, min_repeat=3, vault=vault)
    assert "Nothing to distill" in out


def test_distill_finds_recurring_tag(vault):
    for i in range(3):
        api.memory_ingest(case_id=f"c-{i}", lesson=f"lesson {i} about deployment", tags=["部署"], vault=vault)
    out = api.memory_distill(window_days=30, min_repeat=3, vault=vault)
    assert "部署" in out
    assert any(p.name.startswith("distill-") for p in vault.consolidations_dir.glob("*.md"))


def test_not_initialized_returns_hint(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBRAIN_VAULT", str(tmp_path / "nope"))
    out = api.memory_query("x")
    assert "agentbrain init" in out
