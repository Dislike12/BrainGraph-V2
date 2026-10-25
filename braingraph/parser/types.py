from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ParsedSymbol:
    name: str
    kind: str
    line_start: int
    line_end: int
    signature: str | None = None


@dataclass(slots=True)
class ParsedRelation:
    source_type: str
    source_key: str
    target_type: str
    target_key: str
    relation_type: str
    confidence: float = 1.0
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedFile:
    relative_path: str
    absolute_path: str
    language: str
    content: str
    content_hash: str
    size_bytes: int
    token_estimate: int
    symbols: list[ParsedSymbol] = field(default_factory=list)
    relations: list[ParsedRelation] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
