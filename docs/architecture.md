# BrainGraph Architecture

BrainGraph is now a package-first CLI system with project-local outputs.

Core layers:

- `parser`: scans the repository and extracts files, symbols, imports, routes, APIs, and components
- `database`: stores projects, files, symbols, relations, summaries, embeddings, and diagnostics in SQLite
- `graph_engine`: builds a NetworkX relationship graph, exports `graph.json`, renders `graph.html`, and computes module paths
- `memory`: chunks code and provides Chroma-backed or SQLite lexical retrieval
- `reporting`: writes `BRAIN_REPORT.md`
- `integrations`: generates project-local BrainGraph-first instruction files for Codex, Claude, Cursor, Gemini, and Copilot
- `watcher`: observes repository changes and refreshes `.braingraph`
- `web`: local read/query API and dashboard for the project selected by the CLI
- `cli`: the public product surface; scans in the terminal and launches the local dashboard URL

Generated project data is stored under `.braingraph/`:

- `memory.db`
- `embeddings.db`
- `graph.json`
- `graph.html`
- `BRAIN_REPORT.md`
- `summaries/`
- `cache/`
- `integrations/`
- `dashboard.json`
- `usage.json`

The browser does not select or scan repositories. `braingraph scan <path>` indexes the selected repository before starting the dashboard. Approximate cumulative request context and estimated savings are stored locally in `usage.json`.
