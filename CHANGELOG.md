# Changelog

## 0.2.0 - Unreleased

- Add terminal-first `scan` workflow that indexes a repository and launches its local dashboard URL.
- Store project indexes and cumulative approximate context usage in `.braingraph/`.
- Add a local dashboard and API for repository statistics, graph inspection, retrieval, source references, diagnostics, and optional AI actions.
- Use Tree-sitter syntax trees to extract JavaScript and TypeScript symbols and imports.
- Include query-matched source lines before summaries so small repositories do not receive metadata-only context.
- Do not accrue token savings for empty/no-match retrievals, and label summary-size compression separately from query-context reduction.
- Persist cumulative approximate prepared-context and estimated-savings totals per project.
- Keep AI provider configuration optional and require retrieved source context before an AI request.
- Preserve the existing V1 CLI and indexing capabilities where compatible.

## 0.1.1 - 2026-04-21

- Initial published V1 package release. See the PyPI release history for its exact contents.