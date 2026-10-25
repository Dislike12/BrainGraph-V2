from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select

from braingraph.config import BrainGraphConfig
from braingraph.database.models import CodeFile, Diagnostic, Embedding, Relation, Summary, Symbol
from braingraph.database.repository import clear_project_scan, get_or_create_project
from braingraph.database.session import create_session_factory
from braingraph.diagnostics import run_diagnostics
from braingraph.graph_engine.builder import GraphEngine
from braingraph.memory.chunker import chunk_text
from braingraph.memory.retriever import RetrievalEngine
from braingraph.memory.vector_store import VectorMemory
from braingraph.parser.scanner import ProjectScanner
from braingraph.parser.utils import estimate_tokens
from braingraph.reporting import build_brain_report
from braingraph.summarizer import summarize_file


class BrainGraphService:
    def __init__(self, project_path: str | Path) -> None:
        self.config = BrainGraphConfig.load(project_path)
        self.config.ensure_dirs()
        self.session_factory = create_session_factory(self.config.db_path)
        self.memory = VectorMemory(self.config.embeddings_path)

    def init_project(self) -> dict:
        self.config.ensure_dirs()
        self.config.save()
        return self.scan()

    def scan(self) -> dict:
        scanner = ProjectScanner(self.config)
        parsed_files = scanner.scan()
        file_lookup = self._build_file_lookup(parsed_files)
        self.memory.reset()
        all_chunks = []
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            clear_project_scan(session, project.id)
            session.execute(delete(Embedding).where(Embedding.project_id == project.id))
            for parsed in parsed_files:
                file = CodeFile(
                    project_id=project.id,
                    path=parsed.relative_path,
                    language=parsed.language,
                    size_bytes=parsed.size_bytes,
                    content_hash=parsed.content_hash,
                    token_estimate=parsed.token_estimate,
                )
                session.add(file)
                session.flush()
                for symbol in parsed.symbols:
                    session.add(
                        Symbol(
                            project_id=project.id,
                            file_id=file.id,
                            name=symbol.name,
                            kind=symbol.kind,
                            line_start=symbol.line_start,
                            line_end=symbol.line_end,
                            signature=symbol.signature,
                        )
                    )
                for relation in parsed.relations:
                    session.add(
                        Relation(
                            project_id=project.id,
                            source_type=relation.source_type,
                            source_key=relation.source_key,
                            target_type=relation.target_type,
                            target_key=relation.target_key,
                            relation_type=relation.relation_type,
                            confidence=relation.confidence,
                            metadata_json=json.dumps(relation.metadata),
                        )
                    )
                    resolved_file = self._resolve_relation_target(
                        source_path=parsed.relative_path,
                        target_key=relation.target_key,
                        target_type=relation.target_type,
                        lookup=file_lookup,
                    )
                    if resolved_file:
                        session.add(
                            Relation(
                                project_id=project.id,
                                source_type="file",
                                source_key=parsed.relative_path,
                                target_type="file",
                                target_key=resolved_file,
                                relation_type="depends_on",
                                confidence=0.95,
                                metadata_json=json.dumps({"from": relation.target_key}),
                            )
                        )
                summary = summarize_file(parsed)
                session.add(Summary(project_id=project.id, file_id=file.id, summary=summary))
                (self.config.summaries_dir / f"{parsed.relative_path.replace('/', '__')}.md").write_text(
                    summary, encoding="utf-8"
                )
                chunks = chunk_text(parsed.relative_path, parsed.content)
                all_chunks.extend(chunks)
                for chunk in chunks:
                    session.add(
                        Embedding(
                            project_id=project.id,
                            file_id=file.id,
                            chunk_id=chunk.chunk_id,
                            content=chunk.content,
                            vector_ref=chunk.chunk_id,
                            token_estimate=chunk.token_estimate,
                        )
                    )
            self.memory.add_chunks(all_chunks)
            diagnostics = run_diagnostics(session, project.id, parsed_files)
            session.commit()
            graph_engine = GraphEngine(session, project.id)
            graph_data = graph_engine.export(self.config.graph_json_path)
            graph_engine.export_html(self.config.graph_html_path)
            stats = self.stats()
            self.config.report_path.write_text(
                build_brain_report(
                    project_name=project.name,
                    project_path=self.config.project_path,
                    stats=stats,
                    diagnostics=[
                        {
                            "code": item.code,
                            "severity": item.severity,
                            "message": item.message,
                            "file_path": item.file_path,
                        }
                        for item in diagnostics
                    ],
                    graph_data=graph_data,
                ),
                encoding="utf-8",
            )
            return {
                "project_id": project.id,
                "files": len(parsed_files),
                "chunks": len(all_chunks),
                "diagnostics": len(diagnostics),
                "output_dir": str(self.config.output_dir),
            }

    def stats(self) -> dict:
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            files = session.scalars(select(CodeFile).where(CodeFile.project_id == project.id)).all()
            raw_tokens = sum(file.token_estimate for file in files)
            summaries = session.scalars(select(Summary).where(Summary.project_id == project.id)).all()
            summary_tokens = sum(estimate_tokens(summary.summary) for summary in summaries)
            summary_reduction = (
                0 if raw_tokens == 0 else round(max(0, 1 - summary_tokens / raw_tokens) * 100, 2)
            )
            return {
                "project": project.name,
                "total_files": len(files),
                "raw_tokens": raw_tokens,
                "summary_tokens": min(raw_tokens, summary_tokens),
                "summary_reduction_percent": summary_reduction,
            }

    def retrieve(self, query: str, limit: int = 8) -> dict:
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            return RetrievalEngine(session, project.id, self.memory).retrieve(query, limit)

    def graph(self, output_path: Path | None = None) -> dict:
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            engine = GraphEngine(session, project.id)
            target = output_path or self.config.graph_json_path
            return engine.export(target)

    def graph_html(self, output_path: Path | None = None) -> Path:
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            engine = GraphEngine(session, project.id)
            return engine.export_html(output_path or self.config.graph_html_path)

    def diagnostics(self) -> list[dict]:
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            items = session.scalars(
                select(Diagnostic).where(Diagnostic.project_id == project.id)
            ).all()
            if not items:
                items = run_diagnostics(session, project.id)
            session.commit()
            return [
                {
                    "code": item.code,
                    "severity": item.severity,
                    "message": item.message,
                    "file_path": item.file_path,
                }
                for item in items
            ]

    def export_context(self, query: str, output_path: Path) -> Path:
        result = self.retrieve(query)
        output_path.write_text(result["context"], encoding="utf-8")
        return output_path

    def explain(self, query: str, limit: int = 12) -> dict:
        result = self.retrieve(query, limit)
        diagnostics = self.diagnostics()
        explanation = [
            f"Query: {query}",
            "",
            "Relevant files:",
            *(f"- {file}" for file in result["files"]),
            "",
            f"Token reduction: raw={result['raw_tokens']} compact={result['context_tokens']}",
            "",
            "Context:",
            result["context"] or "No compact context found.",
        ]
        if diagnostics:
            explanation.extend(["", "Diagnostics:", *(f"- {item['message']}" for item in diagnostics[:8])])
        return {
            "query": query,
            "files": result["files"],
            "text": "\n".join(explanation),
            "context_tokens": result["context_tokens"],
            "raw_tokens": result["raw_tokens"],
        }

    def shortest_path(self, source: str, target: str) -> list[str]:
        with self.session_factory() as session:
            project = get_or_create_project(session, self.config.project_path)
            return GraphEngine(session, project.id).shortest_path(source, target)

    def _build_file_lookup(self, parsed_files: list) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for parsed in parsed_files:
            path = Path(parsed.relative_path)
            normalized = path.as_posix().lower()
            lookup[normalized] = parsed.relative_path
            lookup[path.with_suffix("").as_posix().lower()] = parsed.relative_path
            lookup[path.stem.lower()] = parsed.relative_path
            lookup[path.with_suffix("").as_posix().replace("/", ".").lower()] = parsed.relative_path
        return lookup

    def _resolve_relation_target(
        self,
        source_path: str,
        target_key: str,
        target_type: str,
        lookup: dict[str, str],
    ) -> str | None:
        if target_type != "module":
            return None
        raw = target_key.strip().replace("\\", "/").lower()
        candidates = [raw]
        source_parent = Path(source_path).parent
        if raw.startswith("."):
            resolved = (source_parent / raw).as_posix().lower()
            candidates.extend(
                [
                    resolved,
                    resolved.removesuffix(".py"),
                    resolved.removesuffix(".ts"),
                    resolved.removesuffix(".tsx"),
                    resolved.removesuffix(".js"),
                    resolved.removesuffix(".jsx"),
                ]
            )
        for suffix in ("", ".py", ".ts", ".tsx", ".js", ".jsx", "/index.py", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"):
            for candidate in candidates:
                key = f"{candidate}{suffix}".lower()
                if key in lookup:
                    return lookup[key]
        return lookup.get(raw)
