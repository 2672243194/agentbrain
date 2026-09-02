"""Small retrieval-quality gate covering common agent memory queries."""

from agentbrain.models import Lesson
from agentbrain.retrieval import search_lessons


CORPUS = [
    Lesson("proxy-lesson-01", "proxy", "GitHub proxy connection", "GitHub 连接失败时配置 Clash HTTP proxy 127.0.0.1", ["github", "proxy"]),
    Lesson("python-lesson-01", "python", "Python module shadowing", "python -m 被同名源码目录遮蔽时使用 isolated mode", ["python", "module"]),
    Lesson("mcp-lesson-01", "mcp", "MCP startup timeout", "MCP server 启动超时时检查 command、cwd 和环境变量", ["mcp", "timeout"]),
    Lesson("npm-lesson-01", "npm", "npm publish authentication", "npm publish 返回 ENEEDAUTH 时重新执行 npm login", ["npm", "eneedauth"]),
    Lesson("git-lesson-01", "git", "Release tag workflow", "发布前创建并推送 Git tag", ["git", "release"]),
    Lesson("windows-lesson-01", "windows", "Windows native administration", "Windows 策略受限时使用 PowerShell cmdlet", ["windows", "powershell"]),
]

CASES = [
    ("github 无法连接 代理", "proxy-lesson-01"),
    ("python module 同名目录遮蔽", "python-lesson-01"),
    ("MCP server timeout cwd", "mcp-lesson-01"),
    ("ENEEDAUTH npm", "npm-lesson-01"),
    ("release git tag", "git-lesson-01"),
    ("Windows PowerShell 策略", "windows-lesson-01"),
]


def test_retrieval_quality_gate():
    reciprocal_ranks = []
    recalled = 0
    for query, expected in CASES:
        ranked = [lesson.lesson_id for lesson, _ in search_lessons(CORPUS, query)[:5]]
        if expected in ranked:
            recalled += 1
            reciprocal_ranks.append(1 / (ranked.index(expected) + 1))
        else:
            reciprocal_ranks.append(0)

    recall_at_5 = recalled / len(CASES)
    mrr_at_5 = sum(reciprocal_ranks) / len(CASES)
    assert recall_at_5 == 1.0
    assert mrr_at_5 >= 0.9
