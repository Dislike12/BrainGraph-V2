from pathlib import Path

from braingraph.memory.chunker import chunk_text
from braingraph.memory.vector_store import VectorMemory


def test_vector_memory_lexical_search(tmp_path: Path) -> None:
    memory = VectorMemory(tmp_path / "embeddings.db")
    memory.reset()
    memory.add_chunks(chunk_text("auth.py", "def login(): issue_jwt_token()"))
    hits = memory.search("login jwt", limit=3)
    assert hits
    assert hits[0]["file_path"] == "auth.py"
