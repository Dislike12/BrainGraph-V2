from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import networkx as nx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from braingraph.config import BrainGraphConfig
from braingraph.database.models import CodeFile, Relation, Symbol
from braingraph.database.repository import get_or_create_project
from braingraph.parser.utils import estimate_tokens
from braingraph.service import BrainGraphService

logger = logging.getLogger("braingraph.web")
load_dotenv()
WEB_DIR = Path(__file__).with_name("webui")


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=8, ge=1, le=30)
    max_tokens: int = Field(default=1200, ge=32, le=8000)


class ActionRequest(BaseModel):
    action: str = Field(min_length=2, max_length=80)
    query: str = Field(min_length=2, max_length=2000)


class DashboardState:
    def __init__(self) -> None:
        self.lock = Lock()
        self.usage_lock = Lock()
        self.project_path: Path | None = None
        self.service: BrainGraphService | None = None
        self.scan_seconds: float | None = None
        self.scanning = False
        self.last_error: str | None = None
        configured_path = os.getenv("BRAINGRAPH_PROJECT")
        if configured_path:
            self.select_project(Path(configured_path))

    def select_project(self, path: Path) -> BrainGraphService:
        resolved = path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ValueError("The selected project folder does not exist.")
        load_dotenv(resolved / ".env")
        self.project_path = resolved
        self.service = BrainGraphService(resolved)
        self.scan_seconds = self._read_scan_seconds(self.service.config)
        self.last_error = None
        return self.service

    @staticmethod
    def _read_scan_seconds(config: BrainGraphConfig) -> float | None:
        path = config.output_dir / "dashboard.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("scan_seconds")
            return float(value) if value is not None else None
        except (OSError, ValueError, TypeError):
            return None


state = DashboardState()
app = FastAPI(title="BrainGraph V2", docs_url="/api/docs", redoc_url=None)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


def _service() -> BrainGraphService:
    if state.service is None:
        raise HTTPException(status_code=409, detail="Select a repository to begin.")
    return state.service


def _require_index(service: BrainGraphService) -> None:
    if not service.config.db_path.is_file():
        raise HTTPException(status_code=409, detail="This repository has not been scanned yet.")


def _usage(service: BrainGraphService) -> dict[str, int]:
    path = service.config.output_dir / "usage.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "requests": int(data.get("requests", 0)),
            "raw_tokens": int(data.get("raw_tokens", 0)),
            "context_tokens": int(data.get("context_tokens", 0)),
            "saved_tokens": int(data.get("saved_tokens", 0)),
        }
    except (OSError, ValueError, TypeError):
        return {"requests": 0, "raw_tokens": 0, "context_tokens": 0, "saved_tokens": 0}


def _record_usage(service: BrainGraphService, raw_tokens: int, context_tokens: int) -> dict[str, int]:
    with state.usage_lock:
        usage = _usage(service)
        usage["requests"] += 1
        usage["raw_tokens"] += raw_tokens
        usage["context_tokens"] += context_tokens
        usage["saved_tokens"] += max(0, raw_tokens - context_tokens)
        path = service.config.output_dir / "usage.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(usage, indent=2), encoding="utf-8")
        temporary.replace(path)
        return usage


@app.get("/", response_class=HTMLResponse)
def dashboard() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "project_path": str(state.project_path) if state.project_path else None,
        "project_name": state.project_path.name if state.project_path else None,
        "indexed": bool(state.service and state.service.config.db_path.is_file()),
        "scanning": state.scanning,
        "scan_seconds": state.scan_seconds,
        "last_error": state.last_error,
        "ai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "project_data_dir": str(state.service.config.output_dir) if state.service else None,
    }


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    service = _service()
    _require_index(service)
    base = service.stats()
    with service.session_factory() as session:
        project = get_or_create_project(session, service.config.project_path)
        counts = {
            "symbols": session.scalar(select(func.count(Symbol.id)).where(Symbol.project_id == project.id)) or 0,
            "relations": session.scalar(select(func.count(Relation.id)).where(Relation.project_id == project.id)) or 0,
            "files": session.scalar(select(func.count(CodeFile.id)).where(CodeFile.project_id == project.id)) or 0,
        }
        language_rows = session.execute(
            select(CodeFile.language, func.count(CodeFile.id))
            .where(CodeFile.project_id == project.id)
            .group_by(CodeFile.language)
            .order_by(func.count(CodeFile.id).desc())
        ).all()
    graph_data = service.graph()
    warnings = sum(1 for item in service.diagnostics() if item.get("severity") in {"warning", "error"})
    return {
        **base,
        **counts,
        "nodes": len(graph_data["nodes"]),
        "edges": len(graph_data["edges"]),
        "scan_seconds": state.scan_seconds,
        "languages": [{"name": name, "files": count} for name, count in language_rows],
        "diagnostics": warnings,
        "usage": _usage(service),
    }


@app.get("/api/graph")
def graph() -> dict[str, Any]:
    service = _service()
    _require_index(service)
    data = service.graph()
    graph = nx.MultiDiGraph()
    for node in data["nodes"]:
        graph.add_node(str(node.get("id", node.get("label", "node"))), **node)
    for edge in data["edges"]:
        graph.add_edge(edge["source"], edge["target"], **edge)
    degree = dict(graph.degree())
    visible_nodes = sorted(
        data["nodes"],
        key=lambda item: (-degree.get(str(item.get("id")), 0), str(item.get("label", ""))),
    )[:350]
    visible_ids = {item.get("id") for item in visible_nodes}
    visible_edges = [edge for edge in data["edges"] if edge["source"] in visible_ids and edge["target"] in visible_ids][:700]
    return {"nodes": visible_nodes, "edges": visible_edges, "total_nodes": len(data["nodes"]), "total_edges": len(data["edges"])}


@app.get("/api/diagnostics")
def diagnostics() -> list[dict[str, Any]]:
    service = _service()
    _require_index(service)
    return service.diagnostics()


@app.post("/api/query")
def query(request: QueryRequest) -> dict[str, Any]:
    service = _service()
    _require_index(service)
    result = service.retrieve(request.query, request.limit)
    context = str(result["context"])
    if estimate_tokens(context) > request.max_tokens:
        low, high = 0, len(context)
        while low < high:
            middle = (low + high + 1) // 2
            if estimate_tokens(context[:middle]) <= request.max_tokens:
                low = middle
            else:
                high = middle - 1
        result["context"] = context[:low].rsplit("\n", 1)[0]
        result["context_tokens"] = estimate_tokens(result["context"]) if result["context"] else 0
    raw_tokens = int(result["raw_tokens"])
    context_tokens = int(result["context_tokens"])
    has_context = bool(str(result["context"]).strip())
    result["context_savings_percent"] = (
        round(max(0, 1 - context_tokens / raw_tokens) * 100, 2) if raw_tokens and has_context else None
    )
    result["references"] = _references(service, result["files"])
    result["cumulative_usage"] = (
        _record_usage(service, raw_tokens, context_tokens) if has_context else _usage(service)
    )
    return result


@app.post("/api/action")
def action(request: ActionRequest) -> dict[str, Any]:
    context = query(QueryRequest(query=request.query, limit=12))
    if not str(context["context"]).strip():
        return {
            "available": False,
            "message": "No matching indexed source was found. Try another query or rescan the repository.",
            "context": context,
            "text": "",
        }
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "available": False,
            "message": "AI provider is not configured. Add OPENAI_API_KEY to .env and restart BrainGraph.",
            "context": context,
            "text": "",
        }
    action_prompts = {
        "explain": "Explain this project using only the retrieved source context. Cite file paths and line ranges.",
        "bugs": "Review the retrieved source for plausible bugs. Report evidence and file/line references; distinguish risks from confirmed defects.",
        "architecture": "Summarize the architecture supported by the retrieved context. Cite file paths and relationships.",
        "refactor": "Suggest small, evidence-based refactors grounded in the retrieved context. Cite files and explain trade-offs.",
        "ask": "Answer the developer's question using only the retrieved source context. Cite file paths and line ranges; say when evidence is insufficient.",
    }
    action_key = request.action.lower()
    if action_key not in action_prompts:
        raise HTTPException(status_code=400, detail="Unknown AI action.")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": f"{action_prompts[action_key]}\n\nRetrieved repository context:\n{context['context']}"},
            {"role": "user", "content": request.query},
        ],
    }
    http_request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(http_request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
        text = body["choices"][0]["message"]["content"]
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError) as exc:
        logger.warning("AI provider request failed: %s", exc)
        return {"available": True, "error": f"AI request failed: {exc}", "context": context, "text": ""}
    return {"available": True, "context": context, "text": str(text)}


@app.get("/api/file")
def file(path: str, start: int = 1) -> dict[str, Any]:
    service = _service()
    _require_index(service)
    candidate = (service.config.project_path / path).resolve()
    try:
        candidate.relative_to(service.config.project_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path must stay inside the selected repository.") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Source file not found.")
    try:
        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read source file: {exc}") from exc
    start = max(1, min(start, max(1, len(lines))))
    return {"path": path, "start": start, "lines": lines[start - 1 : start + 140]}


def _references(service: BrainGraphService, files: list[str]) -> list[dict[str, Any]]:
    if not files:
        return []
    with service.session_factory() as session:
        rows = session.scalars(select(CodeFile).where(CodeFile.path.in_(files))).all()
        by_path = {item.path: item for item in rows}
        references = []
        for path in files:
            file_record = by_path.get(path)
            if file_record is None:
                continue
            symbols = session.scalars(
                select(Symbol).where(Symbol.file_id == file_record.id).order_by(Symbol.line_start).limit(6)
            ).all()
            references.append({
                "path": path,
                "symbols": [{"name": symbol.name, "kind": symbol.kind, "line": symbol.line_start} for symbol in symbols],
            })
        return references


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("braingraph.web:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), reload=False)
