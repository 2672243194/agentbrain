# Changelog

## 0.6.0 — 2026-09-07

## Changes

- Add shared MCP server instructions for profile lookup, selective retrieval, applicability checks and verified learning under host authorization rules.
- Preserve client-rule migrations and customized content. MCP 1.3+ supports server instructions; older SDKs retain tools with a clear compatibility notice.
- Improve identifier/CJK retrieval and relevance ranking, reuse bounded tokenization results, and exclude expired or superseded recommendations.
- Return query-matching excerpts and one plain-text MCP payload. Keep explicit reads bounded and avoid repeated full-text content.
- Preserve handwritten Markdown, metadata, comments and line endings when recording reads; handle concurrent reads and malformed input safely.
- Reject credential-shaped profile suggestions and unsafe lesson filenames.

## Behavior and compatibility

- Reading a superseded ID points to its replacement. Expired content remains available by explicit ID with a warning and does not increase usage.
- Requests containing more than 10 unique read IDs are rejected rather than silently truncated.
- Restart the agentbrain MCP service after upgrading. Instructions guide supporting clients; they cannot guarantee that every client invokes tools.
- No new dependencies. SDK 2.0.0 was exercised locally; MCP 1.x compatibility was checked against official source and constructor-contract tests.

## Validation

- Windows / Python 3.10: 299 tests passed.
- Real stdio initialization, no Vault access during initialization, repeat connections, tool interfaces, text-only output and rule migrations verified.
