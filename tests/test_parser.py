from pathlib import Path

from braingraph.parser.engine import CodeParser


def test_python_parser_extracts_symbols_and_routes(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text(
        """
from fastapi import FastAPI
app = FastAPI()

class UserService:
    pass

@app.post("/login")
def login(username: str):
    return {"ok": True}
""",
        encoding="utf-8",
    )
    parsed = CodeParser().parse(source, tmp_path, "python")
    names = {symbol.name for symbol in parsed.symbols}
    assert "UserService" in names
    assert "login" in names
    assert "POST /login" in names
    assert "fastapi" in parsed.imports


def test_tsx_parser_extracts_component_and_fetch(tmp_path: Path) -> None:
    source = tmp_path / "Navbar.tsx"
    source.write_text(
        """
import React from "react"
export const Navbar = () => {
  fetch("/api/me")
  return <Logo />
}
""",
        encoding="utf-8",
    )
    parsed = CodeParser().parse(source, tmp_path, "typescriptreact")
    assert any(symbol.name == "Navbar" and symbol.kind == "component" for symbol in parsed.symbols)
    assert any(relation.relation_type == "fetches" for relation in parsed.relations)


def test_python_parser_records_syntax_errors(tmp_path: Path) -> None:
    source = tmp_path / "broken.py"
    source.write_text("def broken(:\n    pass\n", encoding="utf-8")
    parsed = CodeParser().parse(source, tmp_path, "python")
    assert parsed.warnings
    assert parsed.warnings[0].startswith("python_syntax_error:")
