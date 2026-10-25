from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from braingraph.cli import main as cli_main

runner = CliRunner()
EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "quickstart"


def test_documented_quickstart_indexes_and_queries_example(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "quickstart"
    shutil.copytree(
        EXAMPLE_DIR,
        project,
        ignore=shutil.ignore_patterns("README.md", ".braingraph", "braingraph-out"),
    )
    monkeypatch.setattr(cli_main, "open_dashboard", lambda *_args, **_kwargs: None)

    scan_result = runner.invoke(cli_main.app, ["scan", str(project), "--no-open"])
    assert scan_result.exit_code == 0, scan_result.stdout

    output_dir = project / ".braingraph"
    assert (output_dir / "graph.json").is_file()
    assert (output_dir / "graph.html").is_file()
    assert (output_dir / "BRAIN_REPORT.md").is_file()
    assert (output_dir / "dashboard.json").is_file()

    query_result = runner.invoke(
        cli_main.app,
        ["query", "login authentication", "--project", str(project)],
    )
    assert query_result.exit_code == 0, query_result.stdout
    assert "auth.py" in query_result.stdout
