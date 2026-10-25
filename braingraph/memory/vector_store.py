from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from pathlib import Path

from braingraph.memory.chunker import CodeChunk

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}|/[A-Za-z0-9_./:-]+")


def tokenize(text: str) -> list[str]:
    return [item.lower() for item in TOKEN_RE.findall(text)]


class VectorMemory:
    """Chroma-backed memory with a SQLite lexical fallback."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.chroma_dir = storage_path.with_suffix("")
        self._collection = None
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.chroma_dir))
            self._collection = client.get_or_create_collection("braingraph_chunks")
        except Exception:  # noqa: BLE001 - Chroma is optional; SQLite remains the supported fallback.
            self._collection = None
        self._init_sqlite()

    def _init_sqlite(self) -> None:
        with sqlite3.connect(self.storage_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, file_path TEXT, content TEXT, tokens TEXT)"
            )
            conn.commit()

    def reset(self) -> None:
        with sqlite3.connect(self.storage_path) as conn:
            conn.execute("DELETE FROM chunks")
            conn.commit()
        if self._collection is not None:
            existing = self._collection.get()
            ids = existing.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)

    def add_chunks(self, chunks: list[CodeChunk]) -> None:
        if not chunks:
            return
        with sqlite3.connect(self.storage_path) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO chunks (chunk_id, file_path, content, tokens) VALUES (?, ?, ?, ?)",
                [
                    (chunk.chunk_id, chunk.file_path, chunk.content, " ".join(tokenize(chunk.content)))
                    for chunk in chunks
                ],
            )
            conn.commit()
        if self._collection is not None:
            self._collection.upsert(
                ids=[chunk.chunk_id for chunk in chunks],
                documents=[chunk.content for chunk in chunks],
                metadatas=[{"file_path": chunk.file_path} for chunk in chunks],
            )

    def search(self, query: str, limit: int = 8) -> list[dict[str, str | float]]:
        if self._collection is not None:
            try:
                result = self._collection.query(query_texts=[query], n_results=limit)
                ids = result.get("ids", [[]])[0]
                docs = result.get("documents", [[]])[0]
                metas = result.get("metadatas", [[]])[0]
                distances = result.get("distances", [[]])[0] if result.get("distances") else []
                return [
                    {
                        "chunk_id": ids[i],
                        "file_path": metas[i].get("file_path", ""),
                        "content": docs[i],
                        "score": float(1 / (1 + distances[i])) if i < len(distances) else 1.0,
                    }
                    for i in range(len(ids))
                ]
            except Exception:  # noqa: BLE001 - a Chroma query failure falls back to SQLite search.
                return self._lexical_search(query, limit)
        return self._lexical_search(query, limit)

    def _lexical_search(self, query: str, limit: int) -> list[dict[str, str | float]]:
        query_counts = Counter(tokenize(query))
        if not query_counts:
            return []
        rows: list[tuple[str, str, str, str]] = []
        with sqlite3.connect(self.storage_path) as conn:
            rows = list(conn.execute("SELECT chunk_id, file_path, content, tokens FROM chunks"))
        scored: list[dict[str, str | float]] = []
        q_norm = math.sqrt(sum(value * value for value in query_counts.values()))
        for chunk_id, file_path, content, tokens in rows:
            counts = Counter(tokens.split())
            dot = sum(query_counts[token] * counts.get(token, 0) for token in query_counts)
            if dot == 0:
                continue
            norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
            scored.append(
                {
                    "chunk_id": chunk_id,
                    "file_path": file_path,
                    "content": content,
                    "score": dot / (q_norm * norm),
                }
            )
        return sorted(scored, key=lambda item: float(item["score"]), reverse=True)[:limit]
