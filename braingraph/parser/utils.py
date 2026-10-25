from __future__ import annotations

import hashlib
import re
from pathlib import Path

from braingraph.config import IGNORE_DIRS, SUPPORTED_EXTENSIONS


def estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\w+|[^\s\w]", text)) // 2)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def should_ignore(path: Path, root: Path, ignore_dirs: set[str] | None = None) -> bool:
    ignore = ignore_dirs or IGNORE_DIRS
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in ignore for part in rel_parts)


def detect_language(path: Path) -> str | None:
    return SUPPORTED_EXTENSIONS.get(path.suffix.lower())


def read_text_lossy(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
