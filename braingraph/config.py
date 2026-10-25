from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".braingraph",
    "braingraph-out",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".qa",
    ".codex",
    ".claude",
    ".cursor",
    ".gemini",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "coverage",
    ".next",
    ".turbo",
}

SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".html": "html",
    ".css": "css",
    ".json": "json",
}


@dataclass(slots=True)
class BrainGraphConfig:
    project_path: Path
    output_dir: Path
    cache_dir: Path
    db_path: Path
    embeddings_path: Path
    summaries_dir: Path
    report_path: Path
    graph_json_path: Path
    graph_html_path: Path
    integrations_dir: Path
    ignore_dirs: set[str] = field(default_factory=lambda: set(IGNORE_DIRS))

    @classmethod
    def for_project(cls, project_path: str | Path) -> BrainGraphConfig:
        root = Path(project_path).expanduser().resolve()
        out = root / ".braingraph"
        return cls(
            project_path=root,
            output_dir=out,
            cache_dir=out / "cache",
            db_path=out / "memory.db",
            embeddings_path=out / "embeddings.db",
            summaries_dir=out / "summaries",
            report_path=out / "BRAIN_REPORT.md",
            graph_json_path=out / "graph.json",
            graph_html_path=out / "graph.html",
            integrations_dir=out / "integrations",
        )

    @classmethod
    def load(cls, project_path: str | Path) -> BrainGraphConfig:
        config = cls.for_project(project_path)
        path = config.output_dir / "config.json"
        if not path.exists():
            return config
        raw = json.loads(path.read_text(encoding="utf-8"))
        saved_ignore_dirs = set(raw.get("ignore_dirs", []))
        config.ignore_dirs = set(IGNORE_DIRS) | saved_ignore_dirs
        return config

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.integrations_dir.mkdir(parents=True, exist_ok=True)

    def save(self) -> None:
        self.ensure_dirs()
        payload: dict[str, Any] = {
            "project_path": str(self.project_path),
            "output_dir": str(self.output_dir),
            "ignore_dirs": sorted(self.ignore_dirs),
        }
        (self.output_dir / "config.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
