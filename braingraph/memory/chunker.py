from __future__ import annotations

from dataclasses import dataclass

from braingraph.parser.utils import estimate_tokens


@dataclass(slots=True)
class CodeChunk:
    chunk_id: str
    file_path: str
    content: str
    token_estimate: int


def chunk_text(file_path: str, content: str, max_chars: int = 2400, overlap: int = 240) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []
    if not content.strip():
        return chunks
    start = 0
    index = 0
    while start < len(content):
        end = min(len(content), start + max_chars)
        snippet = content[start:end]
        chunks.append(
            CodeChunk(
                chunk_id=f"{file_path}:{index}",
                file_path=file_path,
                content=snippet,
                token_estimate=estimate_tokens(snippet),
            )
        )
        if end == len(content):
            break
        start = max(0, end - overlap)
        index += 1
    return chunks
