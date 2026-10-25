# BrainGraph quickstart example

This small project provides a reproducible example for the terminal `scan` and `query` CLI flow. It contains `app.py`, which imports `authenticate` from `auth.py`.

From the repository root, install the development dependencies and run:

```bash
python -m pip install -e ".[dev]"
python -m braingraph.cli.main scan examples/quickstart --no-open
python -m braingraph.cli.main query "login authentication" --project examples/quickstart
```

The scan command indexes the two Python files and creates `.braingraph/graph.json`, `.braingraph/graph.html`, `.braingraph/BRAIN_REPORT.md`, and the local token-usage ledger in the example directory. Without `--no-open`, scanning prints the dashboard URL and opens it in a browser. The query should identify `auth.py` as relevant context. Generated `.braingraph/` data is ignored by Git and can be removed after trying the example.

The test suite copies this checked-in fixture into a temporary directory, runs the same CLI operations, and verifies the generated files and query result. This keeps the sample safe to rerun without adding generated databases or reports to the repository.
