from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from braingraph.database.models import Base


def sqlite_url(path: str | Path) -> str:
    return f"sqlite:///{Path(path).resolve().as_posix()}"


def create_session_factory(db_path: str | Path) -> sessionmaker[Session]:
    engine = create_engine(sqlite_url(db_path), future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, future=True)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
