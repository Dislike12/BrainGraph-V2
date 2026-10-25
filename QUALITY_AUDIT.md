# BrainGraph V2 Quality Audit

Audit date: 2026-10-25. Package under test: `0.2.0`.

## Clean install and terminal scan

The built wheel was installed into an isolated Python 3.12 virtual environment with runtime dependencies. Its generated `braingraph.exe` reported version `0.2.0`. Running the installed command against a two-file fixture completed with:

- 2 files indexed
- 2 chunks created
- 0 diagnostics
- `.braingraph/` created inside the selected fixture project
- graph exports, SQLite index, report, and local URL emitted
- dashboard server started on `http://127.0.0.1:8022`

The fixture's graph contained 10 nodes and 9 edges, including `api.py -> auth.py` with a `depends_on` relation. The scan path was exercised through the installed console script, not only through a source import.

A later query on this tiny 32-estimated-token fixture returned 57 estimated context tokens because it included two source snippets plus summaries. Its reported reduction was 0/not counted, not a fabricated 92%. This is the expected tradeoff for preserving usable source evidence on very small repositories.

## Test and lint results

- `python -m pytest -q BrainGraph-V2/tests`: 26 passed.
- `ruff check BrainGraph-V2`: all checks passed.
- Existing warning: Starlette reports that its `TestClient` integration with `httpx` is deprecated. It does not fail tests.

## Retrieval sample on this repository

The repository index used for this sample contained 43 supported files and an estimated 21,188 source tokens. The table measures retrieval context against the whole indexed source baseline; the same local token estimator is used for both columns.

| Query | Retrieved files | Prepared context tokens | Estimated context reduction |
|---|---:|---:|---:|
| Tree-sitter extracts TypeScript interfaces and imports | 8 | 453 | 97.86% |
| CLI scan creates `.braingraph` and starts dashboard URL | 8 | 290 | 98.63% |
| graph import dependency edge resolution | 8 | 247 | 98.83% |
| AI provider failure handling and no API key | 8 | 491 | 97.68% |
| cumulative estimated tokens saved usage ledger | 8 | 726 | 96.57% |

Each result included source-bearing snippets. Tests additionally assert that a function query returns its function implementation, an error query includes the matching error branch, and unrelated queries produce no fabricated file matches.

## What the percentages mean

These are estimated code-context reductions for the tested query set under a baseline of sending every indexed source file for each task. They do not include the query text or provider instruction overhead; those are common to both compared contexts but still consume tokens. `estimate_tokens` is a local heuristic, not a model tokenizer. Actual provider tokens and billed usage were not verified because no AI credentials were configured. Do not present these sample percentages as a universal guarantee or as provider billing measurements.

A no-match retrieval is now marked as unmeasured and does not accrue a false full-repository saving. The generated `BRAIN_REPORT.md` labels summary-size compression separately; summary size is not used as an AI-context savings claim.

## Remaining caveats

- A successful live response from an external AI provider was not tested; missing credentials and provider/network failures are covered by automated tests.
- Retrieval ranking is lexical/chunk based with graph-neighbor expansion, not a semantic embedding guarantee. The samples establish evidence for these queries only.
- The dashboard server is local-only and has no authentication. Do not expose it on an untrusted network.
