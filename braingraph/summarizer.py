from __future__ import annotations

from braingraph.parser.types import ParsedFile


def summarize_file(parsed: ParsedFile) -> str:
    kinds: dict[str, list[str]] = {}
    for symbol in parsed.symbols:
        kinds.setdefault(symbol.kind, []).append(symbol.name)
    parts = [parsed.language]
    if "class" in kinds:
        parts.append(f"classes {', '.join(kinds['class'][:5])}")
    if "function" in kinds:
        parts.append(f"functions {', '.join(kinds['function'][:6])}")
    if "component" in kinds:
        parts.append(f"components {', '.join(kinds['component'][:5])}")
    if "api" in kinds:
        parts.append(f"api {', '.join(kinds['api'][:4])}")
    if "route" in kinds:
        parts.append(f"routes {', '.join(kinds['route'][:4])}")
    if "variable" in kinds:
        parts.append(f"vars {', '.join(kinds['variable'][:5])}")
    if parsed.imports:
        parts.append(f"imports {', '.join(parsed.imports[:4])}")
    if len(parts) == 1:
        first_lines = " ".join(line.strip() for line in parsed.content.splitlines()[:5] if line.strip())
        parts.append(first_lines[:120] if first_lines else "data or styling")
    return "; ".join(parts)[:320]
