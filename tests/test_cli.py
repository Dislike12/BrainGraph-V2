from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from typer.testing import CliRunner

from braingraph import __version__
from braingraph.cli import main as cli_main
from braingraph.config import BrainGraphConfig
from braingraph.parser.scanner import ProjectScanner

runner = CliRunner()


def test_cli_version_flag_outputs_version() -> None:
    result = runner.invoke(cli_main.app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_project_metadata_uses_package_version_as_source_of_truth() -> None:
    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(project_file.read_text(encoding="utf-8"))
    assert "version" in metadata["project"]["dynamic"]
    assert metadata["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "braingraph.__version__"


def test_cli_watch_supports_seconds_option(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, float | Path | None] = {"project": None, "seconds": None}

    def fake_watch(project_path: Path, duration_seconds: float | None = None) -> None:
        called["project"] = project_path
        called["seconds"] = duration_seconds

    monkeypatch.setattr(cli_main, "watch_project", fake_watch)
    result = runner.invoke(cli_main.app, ["watch", str(tmp_path), "--seconds", "1.5"])
    assert result.exit_code == 0
    assert called["project"] == tmp_path.resolve()
    assert called["seconds"] == 1.5


def test_run_dispatches_init_as_command(tmp_path: Path, monkeypatch) -> None:
    called = {"app": False, "service": False}

    class FakeService:
        def __init__(self, _project: Path) -> None:
            called["service"] = True

        def init_project(self) -> dict[str, str | int]:
            return {"files": 1, "output_dir": "unused"}

    def fake_app() -> None:
        called["app"] = True

    monkeypatch.setattr(cli_main, "BrainGraphService", FakeService)
    monkeypatch.setattr(cli_main, "app", fake_app)
    monkeypatch.setattr(sys, "argv", ["braingraph", "init", str(tmp_path)])
    cli_main.run()
    assert called["app"] is True
    assert called["service"] is False


def test_scanner_ignores_walk_errors(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "app.py"
    src.write_text("def hello():\n    return 'ok'\n", encoding="utf-8")

    def fake_walk(*_args, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror:
            onerror(PermissionError("blocked"))
        yield str(tmp_path), [], ["app.py"]

    monkeypatch.setattr("braingraph.parser.scanner.os.walk", fake_walk)
    config = BrainGraphConfig.for_project(tmp_path)
    files = ProjectScanner(config).iter_files()
    assert files == [src]


def test_scan_command_indexes_in_terminal_and_prints_dashboard_url(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.py").write_text("def run():\n    return 'ready'\n", encoding="utf-8")
    opened: dict[str, object] = {}

    def fake_open_dashboard(project: Path, host: str, port: int, open_browser: bool = True) -> None:
        opened.update(project=project, host=host, port=port, open_browser=open_browser)

    monkeypatch.setattr(cli_main, "open_dashboard", fake_open_dashboard)
    result = runner.invoke(cli_main.app, ["scan", str(tmp_path), "--port", "8012", "--no-open"])

    assert result.exit_code == 0, result.stdout
    assert "Scanned" in result.stdout
    assert (tmp_path / ".braingraph" / "memory.db").is_file()
    assert opened == {"project": tmp_path.resolve(), "host": "127.0.0.1", "port": 8012, "open_browser": False}
