from pathlib import Path

from braingraph.parser.engine import CodeParser


def test_tree_sitter_extracts_typescript_interfaces_functions_and_imports(tmp_path: Path) -> None:
    source = tmp_path / "service.ts"
    source.write_text(
        """import { User } from './models';
export interface Session { token: string }
export const loadUser = async (session: Session): Promise<User> => fetchUser(session.token);
export class UserService { find() { return loadUser(this.session); } }
""",
        encoding="utf-8",
    )

    parsed = CodeParser().parse(source, tmp_path, "typescript")

    assert any(symbol.name == "Session" and symbol.kind == "interface" for symbol in parsed.symbols)
    assert any(symbol.name == "loadUser" and symbol.kind == "function" for symbol in parsed.symbols)
    assert any(symbol.name == "UserService" and symbol.kind == "class" for symbol in parsed.symbols)
    assert "./models" in parsed.imports
