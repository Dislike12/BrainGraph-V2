# BrainGraph V2

Local-first code intelligence for indexing source files, symbols, imports, and graph relationships. V2 preserves the V1 Python package and CLI, adds Tree-sitter JavaScript/TypeScript extraction, and provides a local dashboard with optional source-grounded AI actions.

## Install

After the V2 release is published, install the package into the Python environment used by your terminal, VS Code, Antigravity, Claude Code, or Codex:

```shell
python -m pip install --upgrade braingraph
```

The V2 source checkout can be installed locally before publication with `python -m pip install .`. For development, use an isolated environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

On Windows use `py -3.12 -m pip install .` if `python` is not the desired interpreter; on macOS/Linux use `python3 -m pip install .`. The `braingraph` command is available in terminals using that same environment.

## Scan from a terminal

From the repository you want to index:

```powershell
braingraph scan .
```

BrainGraph scans locally, creates `.braingraph/` inside the selected project, prints a local dashboard URL, opens it in a browser, and keeps the server running in that terminal. Use `Ctrl+C` to stop it. The dashboard is for viewing/querying; it has no repository picker or scan controls.

```powershell
braingraph scan "C:\work\my-project"
braingraph scan . --port 8012
braingraph scan . --no-open
braingraph dashboard .
braingraph update .
braingraph query "authentication flow"
```

`dashboard` opens an existing index without rescanning. `update` rescans in the terminal. The local API docs are at `/api/docs` on the printed URL.

## Project data and token estimates

Each project stores its SQLite index, lexical chunks, graph exports, summaries, report, scan timing, and `usage.json` in `.braingraph/`. This folder is ignored by Git. Rescans rebuild indexed data but preserve the usage ledger.

Approximate context-use metrics accumulate per query:

- baseline: estimated tokens across indexed source files
- prepared context: estimated tokens returned by retrieval
- estimated saved: `max(0, baseline - prepared context)`

These use BrainGraph's local estimator, not the provider tokenizer or billing response. They estimate the context prepared, not proof of the amount sent or billed by an AI service. Historical presentation metrics are not hardcoded.

The generated `BRAIN_REPORT.md` separately reports summary-size reduction (file summaries compared with indexed source). That statistic is not an AI/query context-reduction result and must not be quoted as one.

See [QUALITY_AUDIT.md](QUALITY_AUDIT.md) for the clean-install scan result, representative query measurements, tests, and the limits of those estimates.

Small repositories may show 0% savings: source labels/line references can make a grounded context longer than the raw project. BrainGraph reports that honestly rather than dropping useful evidence to force a target percentage.

## Dashboard and AI

The dashboard shows repository counts, dependency graph, diagnostics, cumulative approximate context usage/savings, retrieval results, and source references. The graph can be filtered, zoomed, panned, and opened into a source preview. The complete graph is exported to `.braingraph/graph.json`.

Scanning and retrieval require no AI key. To enable AI actions, put provider settings in the scanned repository's `.env` or set them in the terminal:

```dotenv
OPENAI_API_KEY=replace-with-your-provider-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

The provider must support OpenAI Chat Completions. Only the question and retrieved context are sent. No matching source means no provider request. The local server binds to `127.0.0.1` and has no authentication; do not expose it to an untrusted network. Never commit a real key.

## Tests

```powershell
python -m pytest -q
ruff check .
```

Tests cover terminal scan and dashboard startup, `.braingraph` persistence, rescans, graph/retrieval behavior, context ceilings and cumulative estimates, empty/no-match repositories, provider failures, safe source previews, and Tree-sitter extraction.

## V1 and V2

| Capability | V1 baseline | V2 |
|---|---|---|
| CLI scanner, SQLite, lexical retrieval, NetworkX graph | Existing | Retained |
| Project data directory | `braingraph-out/` | `.braingraph/` |
| JS/TS Tree-sitter | Parse tree discarded | Extracts declarations/imports |
| Browser app | Static graph export | Local dashboard, metrics, graph, source preview, retrieval and optional AI |
| Scan workflow | CLI scan | Terminal scan prints/opens URL; browser cannot scan |
| Token metrics | Report-level estimate | Persistent approximate context use and estimated savings |

V1 source is preserved separately at <https://github.com/Dislike12/BrainGraph> for comparison. This V2 repository is <https://github.com/Dislike12/BrainGraph-V2>. Zepto and Power BI material is excluded.

## Screenshots

Screenshots are stored in the source checkout under `screenshots/`. They are not required at runtime and are not included in the wheel.
