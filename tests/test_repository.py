from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from braingraph.database.models import Project
from braingraph.database.repository import get_or_create_project


class FakeSession:
    def __init__(self, project_path: str) -> None:
        self.project_path = project_path
        self.project = Project(id=7, path=project_path, name="BrainGraph")
        self.scalar_calls = 0
        self.rollback_called = False
        self.added: list[Project] = []

    def scalar(self, _query: object) -> Project | None:
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return None
        return self.project

    def add(self, project: Project) -> None:
        self.added.append(project)

    def flush(self) -> None:
        raise IntegrityError("insert", {"path": self.project_path}, sqlite3.IntegrityError("duplicate"))

    def rollback(self) -> None:
        self.rollback_called = True


def test_get_or_create_project_recovers_from_duplicate_insert_race(tmp_path: Path) -> None:
    project_path = str(tmp_path.resolve())
    session = FakeSession(project_path)

    project = get_or_create_project(session, tmp_path)

    assert project.path == project_path
    assert session.rollback_called is True
    assert session.scalar_calls == 2
