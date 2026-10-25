from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from braingraph import web
from braingraph.service import BrainGraphService


@pytest.fixture

def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    web.state = web.DashboardState()
    return TestClient(web.app)


def make_repository(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "auth.py").write_text(
        "from pathlib import Path\n\n\ndef authenticate(token: str) -> bool:\n    return bool(token)\n",
        encoding="utf-8",
    )
    (path / "app.py").write_text(
        "from auth import authenticate\n\n\ndef login(token: str) -> bool:\n    return authenticate(token)\n",
        encoding="utf-8",
    )
    return path


def prepare_index(path: Path) -> BrainGraphService:
    service = BrainGraphService(path)
    service.init_project()
    web.state.project_path = path.resolve()
    web.state.service = service
    (service.config.output_dir / "dashboard.json").write_text(
        '{"scan_seconds": 0.1}', encoding="utf-8"
    )
    web.state.scan_seconds = 0.1
    return service


def test_scan_stats_graph_and_query_are_connected(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "sample")
    service = prepare_index(repository)
    assert service.config.output_dir == repository / ".braingraph"
    stats = client.get("/api/stats").json()
    assert stats["files"] == 2
    assert stats["symbols"] >= 2
    assert stats["nodes"] >= stats["files"]
    assert stats["raw_tokens"] > 0
    graph = client.get("/api/graph").json()
    assert graph["total_nodes"] == stats["nodes"]
    assert graph["edges"]

    result = client.post("/api/query", json={"query": "authenticate login", "max_tokens": 64}).json()
    assert "auth.py" in result["files"]
    assert result["context_tokens"] <= 64
    assert result["context_savings_percent"] >= 0
    assert result["references"]
    assert "def authenticate" in result["context"]


def test_retrieval_returns_query_specific_source_lines(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "relevance")
    (repository / "auth.py").write_text(
        "def authenticate(token: str) -> bool:\n"
        "    if not token:\n"
        "        raise ValueError('token required')\n"
        "    return True\n",
        encoding="utf-8",
    )
    service = prepare_index(repository)

    function_context = service.retrieve("authenticate")
    error_context = service.retrieve("ValueError token required")

    assert "def authenticate" in function_context["context"]
    assert "raise ValueError" in error_context["context"]
    assert function_context["context"] != error_context["context"]


def test_repeated_scan_rebuilds_without_duplicate_files(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "repeat")
    service = prepare_index(repository)
    first = service.stats()
    service.scan()
    second = service.stats()

    assert second["total_files"] == first["total_files"] == 2
    assert client.get("/api/stats").json()["files"] == 2


def test_empty_repository_and_invalid_path_states(client: TestClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    service = prepare_index(empty)
    assert service.stats()["total_files"] == 0
    assert client.get("/api/stats").json()["nodes"] == 0


def test_ai_unavailable_still_returns_retrieved_context(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "no-ai")
    prepare_index(repository)

    response = client.post("/api/action", json={"action": "explain", "query": "authenticate token"})

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert "OPENAI_API_KEY" in response.json()["message"]
    assert "auth.py" in response.json()["context"]["files"]


def test_provider_failure_is_reported_without_losing_context(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = make_repository(tmp_path / "provider-failure")
    prepare_index(repository)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(web, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")))

    response = client.post("/api/action", json={"action": "bugs", "query": "authenticate token"})

    assert response.status_code == 200
    assert "offline" in response.json()["error"]
    assert response.json()["context"]["files"]


def test_unmatched_query_returns_empty_context_without_inventing_files(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "no-match")
    prepare_index(repository)

    response = client.post("/api/query", json={"query": "unrelated astronomy"})

    assert response.status_code == 200
    assert response.json()["files"] == []
    assert response.json()["context"] == ""
    assert response.json()["context_savings_percent"] is None
    assert response.json()["cumulative_usage"]["requests"] == 0
    assert not (repository / ".braingraph" / "usage.json").exists()


def test_source_preview_rejects_paths_outside_repository(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "source-boundary")
    prepare_index(repository)

    assert client.get("/api/file", params={"path": "auth.py"}).status_code == 200
    assert client.get("/api/file", params={"path": "../outside.py"}).status_code == 400


def test_dashboard_does_not_expose_repository_scan_controls(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "scanForm" not in response.text
    assert "repoPath" in response.text
    assert not any(route.path == "/api/scan" for route in web.app.routes)


def test_cumulative_usage_survives_service_recreation(client: TestClient, tmp_path: Path) -> None:
    repository = make_repository(tmp_path / "usage")
    prepare_index(repository)
    for _ in range(2):
        response = client.post("/api/query", json={"query": "authenticate token"})
        assert response.status_code == 200

    web.state.service = BrainGraphService(repository)
    usage = client.get("/api/stats").json()["usage"]

    assert usage["requests"] == 2
    assert usage["raw_tokens"] > 0
    assert usage["context_tokens"] > 0
    assert usage["saved_tokens"] >= 0
