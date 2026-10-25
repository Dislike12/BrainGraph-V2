from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from braingraph.parser.types import ParsedFile, ParsedRelation, ParsedSymbol
from braingraph.parser.utils import estimate_tokens, read_text_lossy, sha256_text

try:
    from tree_sitter_language_pack import get_parser
except ImportError:  # pragma: no cover - parser pack is optional
    get_parser = None  # type: ignore[assignment]


class CodeParser:
    """Extracts symbols and relationships from supported code files."""

    def parse(self, path: Path, root: Path, language: str) -> ParsedFile:
        content = read_text_lossy(path)
        rel = path.relative_to(root).as_posix()
        parsed = ParsedFile(
            relative_path=rel,
            absolute_path=str(path),
            language=language,
            content=content,
            content_hash=sha256_text(content),
            size_bytes=path.stat().st_size,
            token_estimate=estimate_tokens(content),
        )
        if language == "python":
            self._parse_python(parsed)
        elif language in {"javascript", "javascriptreact", "typescript", "typescriptreact"}:
            self._parse_js_ts(parsed)
        elif language == "html":
            self._parse_html(parsed)
        elif language == "css":
            self._parse_css(parsed)
        elif language == "json":
            self._parse_json(parsed)
        self._touch_tree_sitter(language, content, parsed)
        return parsed

    def _touch_tree_sitter(self, language: str, content: str, parsed: ParsedFile) -> None:
        if get_parser is None or not content.strip():
            return
        lang_name = {
            "javascriptreact": "javascript",
            "typescriptreact": "tsx",
            "typescript": "typescript",
        }.get(language, language)
        try:
            parser = get_parser(lang_name)
            tree = parser.parse(content.encode("utf-8", errors="ignore"))
        except Exception:  # noqa: BLE001 - parser failures must not block BrainGraph's own scan.
            return
        if language not in {"javascript", "javascriptreact", "typescript", "typescriptreact"}:
            return
        nodes = [tree.root_node]
        seen_symbols = {(symbol.name, symbol.kind) for symbol in parsed.symbols}
        seen_imports = set(parsed.imports)
        while nodes:
            node = nodes.pop()
            node_text = content.encode("utf-8", errors="ignore")[node.start_byte:node.end_byte].decode(
                "utf-8", errors="ignore"
            )
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8", errors="ignore") if name_node is not None else ""
            kind = {
                "function_declaration": "function",
                "generator_function_declaration": "function",
                "class_declaration": "class",
                "interface_declaration": "interface",
                "type_alias_declaration": "type",
                "enum_declaration": "enum",
                "method_definition": "method",
            }.get(node.type)
            if node.type == "variable_declarator":
                value = node.child_by_field_name("value")
                if name and value is not None and value.type in {"arrow_function", "function", "function_expression"}:
                    kind = "component" if name[:1].isupper() else "function"
            if kind and name and (name, kind) not in seen_symbols:
                parsed.symbols.append(
                    ParsedSymbol(
                        name=name,
                        kind=kind,
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        signature=node_text.splitlines()[0].strip()[:240],
                    )
                )
                seen_symbols.add((name, kind))
            if node.type in {"import_statement", "import_declaration"}:
                module = next(
                    (child.text.decode("utf-8", errors="ignore").strip("'\"") for child in node.children if child.type in {"string", "string_fragment"}),
                    None,
                )
                if module and module not in seen_imports:
                    parsed.imports.append(module)
                    parsed.relations.append(
                        ParsedRelation("file", parsed.relative_path, "module", module, "imports", 0.95)
                    )
                    seen_imports.add(module)
            nodes.extend(reversed(node.children))
        if tree.root_node.has_error:
            parsed.warnings.append(f"tree_sitter_syntax_error:{tree.root_node.start_point.row + 1}")

    def _parse_python(self, parsed: ParsedFile) -> None:
        try:
            tree = ast.parse(parsed.content)
        except SyntaxError as exc:
            parsed.warnings.append(f"python_syntax_error:{exc.lineno or 1}:{exc.msg}")
            return
        file_key = parsed.relative_path
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parsed.symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        kind="function",
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=self._python_signature(node),
                    )
                )
            elif isinstance(node, ast.ClassDef):
                parsed.symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        kind="class",
                        line_start=node.lineno,
                        line_end=getattr(node, "end_lineno", node.lineno),
                        signature=f"class {node.name}",
                    )
                )
                for base in node.bases:
                    target = self._ast_name(base)
                    if target:
                        parsed.relations.append(
                            ParsedRelation("class", node.name, "class", target, "extends", 0.8)
                        )
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    modules = [node.module or ""]
                for module in modules:
                    if module:
                        parsed.imports.append(module)
                        parsed.relations.append(
                            ParsedRelation("file", file_key, "module", module, "imports", 0.9)
                        )
            elif isinstance(node, ast.Call):
                target = self._ast_name(node.func)
                if target:
                    parsed.relations.append(
                        ParsedRelation("file", file_key, "function", target, "calls", 0.45)
                    )
        self._parse_python_routes(parsed)

    def _python_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = [arg.arg for arg in node.args.args]
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"

    def _ast_name(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._ast_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        if isinstance(node, ast.Call):
            return self._ast_name(node.func)
        return None

    def _parse_python_routes(self, parsed: ParsedFile) -> None:
        route_re = re.compile(r"@(?:\w+\.)?(get|post|put|patch|delete|router\.(?:get|post|put|patch|delete))\(['\"]([^'\"]+)")
        for idx, line in enumerate(parsed.content.splitlines(), start=1):
            match = route_re.search(line)
            if not match:
                continue
            method = match.group(1).split(".")[-1].upper()
            path = match.group(2)
            name = f"{method} {path}"
            parsed.symbols.append(ParsedSymbol(name=name, kind="api", line_start=idx, line_end=idx))
            parsed.relations.append(
                ParsedRelation("file", parsed.relative_path, "api", name, "defines", 1.0)
            )

    def _parse_js_ts(self, parsed: ParsedFile) -> None:
        lines = parsed.content.splitlines()
        for idx, line in enumerate(lines, start=1):
            for pattern in (
                r"import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]",
                r"require\(['\"]([^'\"]+)['\"]\)",
            ):
                for module in re.findall(pattern, line):
                    parsed.imports.append(module)
                    parsed.relations.append(
                        ParsedRelation("file", parsed.relative_path, "module", module, "imports", 0.9)
                    )
            export_match = re.search(r"export\s+(?:default\s+)?(?:function|class|const|let|var)\s+([A-Za-z_$][\w$]*)", line)
            if export_match:
                parsed.exports.append(export_match.group(1))
            for kind, pattern in (
                ("function", r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
                ("class", r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)"),
                ("component", r"(?:const|let|var)\s+([A-Z][A-Za-z0-9_$]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>"),
                ("variable", r"(?:const|let|var)\s+([a-zA-Z_$][\w$]*)\s*="),
            ):
                match = re.search(pattern, line)
                if match:
                    parsed.symbols.append(
                        ParsedSymbol(match.group(1), kind, idx, idx, line.strip()[:240])
                    )
            for exported in re.findall(r"module\.exports\s*=\s*\{([^}]+)\}", line):
                for name in re.findall(r"[A-Za-z_$][\w$]*", exported):
                    parsed.symbols.append(ParsedSymbol(name, "variable", idx, idx, line.strip()[:240]))
            for method, url in re.findall(r"(?:fetch|axios\.(get|post|put|patch|delete))\(\s*['\"]([^'\"]+)['\"]", line):
                api = f"{(method or 'GET').upper()} {url}"
                parsed.symbols.append(ParsedSymbol(api, "api", idx, idx))
                parsed.relations.append(
                    ParsedRelation("file", parsed.relative_path, "api", api, "fetches", 0.8)
                )
            for route in re.findall(r"<Route[^>]+path=['\"]([^'\"]+)['\"]", line):
                parsed.symbols.append(ParsedSymbol(route, "route", idx, idx))
                parsed.relations.append(
                    ParsedRelation("file", parsed.relative_path, "route", route, "defines", 0.85)
                )
        self._parse_jsx_renders(parsed)

    def _parse_jsx_renders(self, parsed: ParsedFile) -> None:
        for component in set(re.findall(r"<([A-Z][A-Za-z0-9_]*)\b", parsed.content)):
            parsed.relations.append(
                ParsedRelation("file", parsed.relative_path, "component", component, "renders", 0.55)
            )

    def _parse_html(self, parsed: ParsedFile) -> None:
        title = re.search(r"<title>(.*?)</title>", parsed.content, flags=re.IGNORECASE | re.DOTALL)
        if title:
            parsed.symbols.append(ParsedSymbol(title.group(1).strip(), "component", 1, 1))
        for src in re.findall(r"(?:src|href)=['\"]([^'\"]+)['\"]", parsed.content):
            parsed.relations.append(
                ParsedRelation("file", parsed.relative_path, "asset", src, "depends_on", 0.7)
            )

    def _parse_css(self, parsed: ParsedFile) -> None:
        for idx, line in enumerate(parsed.content.splitlines(), start=1):
            for selector in re.findall(r"([.#][A-Za-z0-9_-]+)\s*\{", line):
                parsed.symbols.append(ParsedSymbol(selector, "selector", idx, idx))

    def _parse_json(self, parsed: ParsedFile) -> None:
        try:
            data = json.loads(parsed.content)
        except json.JSONDecodeError as exc:
            parsed.warnings.append(f"json_decode_error:{exc.lineno}:{exc.msg}")
            return
        if isinstance(data, dict):
            for key in ("scripts", "dependencies", "devDependencies"):
                if key in data:
                    parsed.symbols.append(ParsedSymbol(key, "config", 1, 1))
