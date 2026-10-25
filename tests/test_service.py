from pathlib import Path

from braingraph.integrations import install_integration
from braingraph.service import BrainGraphService


def test_service_scans_project_and_writes_outputs(tmp_path: Path) -> None:
    (tmp_path / "auth.py").write_text("def login():\n    return True\n", encoding="utf-8")
    service = BrainGraphService(tmp_path)
    result = service.init_project()
    assert result["files"] == 1
    assert (tmp_path / ".braingraph" / "graph.json").exists()
    assert (tmp_path / ".braingraph" / "graph.html").exists()
    assert (tmp_path / ".braingraph" / "BRAIN_REPORT.md").exists()
    stats = service.stats()
    assert stats["total_files"] == 1
    assert "summary_reduction_percent" in stats
    assert "saved_percent" not in stats
    retrieved = service.retrieve("login")
    assert "auth.py" in retrieved["files"] or retrieved["chunks"]


def test_shortest_path_and_integration_install(tmp_path: Path) -> None:
    (tmp_path / "login.tsx").write_text(
        'import auth from "./auth"\nexport function Login() { return auth() }\n',
        encoding="utf-8",
    )
    (tmp_path / "auth.py").write_text("def auth():\n    return True\n", encoding="utf-8")
    service = BrainGraphService(tmp_path)
    service.init_project()
    route = service.shortest_path("login.tsx", "auth")
    assert route
    integration_file = install_integration(tmp_path, "codex")
    assert integration_file.exists()
    second_install = install_integration(tmp_path, "codex")
    assert second_install == integration_file


def test_service_reports_dead_and_broken_files(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "lonely.css").write_text(".box { color: red; }\n", encoding="utf-8")
    service = BrainGraphService(tmp_path)
    service.init_project()
    diagnostics = service.diagnostics()
    codes = {item["code"] for item in diagnostics}
    assert "python_syntax_error" in codes
    assert "dead_file" in codes
