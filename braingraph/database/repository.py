from __future__ import annotations

from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from braingraph.database.models import CodeFile, Project, Query, Relation, Summary, Symbol


def get_or_create_project(session: Session, project_path: Path) -> Project:
    path = str(project_path.resolve())
    project = session.scalar(select(Project).where(Project.path == path))
    if project:
        return project
    project = Project(path=path, name=project_path.name or "project")
    session.add(project)
    try:
        session.flush()
        return project
    except IntegrityError:
        # Another process may have inserted the same project path between our
        # initial lookup and flush. Roll back the failed insert and fetch it.
        session.rollback()
        existing = session.scalar(select(Project).where(Project.path == path))
        if existing:
            return existing
        raise


def clear_project_scan(session: Session, project_id: int) -> None:
    for model in (Relation, Symbol, Summary, CodeFile):
        session.execute(delete(model).where(model.project_id == project_id))


def count_rows(session: Session, model: type, project_id: int) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(model.project_id == project_id)) or 0)


def record_query(
    session: Session,
    project_id: int,
    query: str,
    response: str,
    raw_tokens: int,
    context_tokens: int,
) -> Query:
    item = Query(
        project_id=project_id,
        query=query,
        response=response,
        raw_tokens=raw_tokens,
        context_tokens=context_tokens,
    )
    session.add(item)
    return item
