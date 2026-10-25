from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from braingraph.database.models import CodeFile, Diagnostic, Relation, Symbol
from braingraph.graph_engine.builder import GraphEngine
from braingraph.parser.types import ParsedFile


def run_diagnostics(session: Session, project_id: int, parsed_files: list[ParsedFile] | None = None) -> list[Diagnostic]:
    session.query(Diagnostic).filter(Diagnostic.project_id == project_id).delete()
    diagnostics: list[Diagnostic] = []
    files = session.scalars(select(CodeFile).where(CodeFile.project_id == project_id)).all()
    by_hash: dict[str, list[CodeFile]] = defaultdict(list)
    symbol_counts: Counter[str] = Counter()
    relation_counts: Counter[str] = Counter()
    if parsed_files:
        for parsed in parsed_files:
            if parsed.symbols:
                symbol_counts[parsed.relative_path] += len(parsed.symbols)
            if parsed.relations:
                relation_counts[parsed.relative_path] += len(parsed.relations)
            for warning in parsed.warnings:
                code, _, detail = warning.partition(":")
                diagnostics.append(
                    Diagnostic(
                        project_id=project_id,
                        code=code,
                        severity="warning",
                        message=detail or warning,
                        file_path=parsed.relative_path,
                    )
                )
    else:
        file_by_id = {file.id: file.path for file in files}
        for symbol in session.scalars(select(Symbol).where(Symbol.project_id == project_id)):
            path = file_by_id.get(symbol.file_id)
            if path:
                symbol_counts[path] += 1
        for relation in session.scalars(select(Relation).where(Relation.project_id == project_id)):
            if relation.source_type == "file":
                relation_counts[relation.source_key] += 1
            if relation.target_type == "file":
                relation_counts[relation.target_key] += 1
    for file in files:
        by_hash[file.content_hash].append(file)
        if file.token_estimate > 3500:
            diagnostics.append(
                Diagnostic(
                    project_id=project_id,
                    code="huge_file",
                    severity="warning",
                    message=f"{file.path} is large and may need focused chunking.",
                    file_path=file.path,
                )
            )
        if symbol_counts[file.path] == 0 and relation_counts[file.path] == 0 and file.language != "json":
            diagnostics.append(
                Diagnostic(
                    project_id=project_id,
                    code="dead_file",
                    severity="info",
                    message=f"{file.path} has no detected symbols or relationships.",
                    file_path=file.path,
                )
            )
    for duplicates in by_hash.values():
        if len(duplicates) > 1:
            diagnostics.append(
                Diagnostic(
                    project_id=project_id,
                    code="duplicate_file",
                    severity="info",
                    message="Duplicate content: " + ", ".join(file.path for file in duplicates[:6]),
                    file_path=duplicates[0].path,
                )
            )
    for cycle in GraphEngine(session, project_id).circular_imports():
        diagnostics.append(
            Diagnostic(
                project_id=project_id,
                code="circular_import",
                severity="warning",
                message="Circular import path: " + " -> ".join(cycle),
                file_path=cycle[0] if cycle else None,
            )
        )
    session.add_all(diagnostics)
    return diagnostics
