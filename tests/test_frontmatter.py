from agentbrain.frontmatter import dump, parse


def test_roundtrip():
    text = dump({"a": 1, "tags": ["x", "y"], "s": "证据链"}, "正文\n第二行")
    meta, body = parse(text)
    assert meta["a"] == 1
    assert meta["tags"] == ["x", "y"]
    assert meta["s"] == "证据链"
    assert "正文" in body
    assert "第二行" in body


def test_parse_without_frontmatter():
    meta, body = parse("# just a heading\n")
    assert meta == {}
    assert body.startswith("# just")


def test_dump_keeps_unicode_readable():
    out = dump({"s": "中文摘要"}, "body")
    assert "中文摘要" in out
    assert out.startswith("---\n")
