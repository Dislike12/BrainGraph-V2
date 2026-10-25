from __future__ import annotations

import os
from pathlib import Path

from braingraph.config import BrainGraphConfig
from braingraph.parser.engine import CodeParser
from braingraph.parser.types import ParsedFile
from braingraph.parser.utils import detect_language, should_ignore


class ProjectScanner:
    def __init__(self, config: BrainGraphConfig) -> None:
        self.config = config
        self.parser = CodeParser()

    def iter_files(self) -> list[Path]:
        root = self.config.project_path
        files: list[Path] = []
        for current_root, dir_names, file_names in os.walk(root, topdown=True, onerror=lambda _error: None):
            current_path = Path(current_root)
            dir_names[:] = [
                name
                for name in dir_names
                if not should_ignore(current_path / name, root, self.config.ignore_dirs)
            ]
            for file_name in file_names:
                path = current_path / file_name
                if should_ignore(path, root, self.config.ignore_dirs):
                    continue
                if detect_language(path):
                    files.append(path)
        return sorted(files)

    def scan(self) -> list[ParsedFile]:
        root = self.config.project_path
        parsed: list[ParsedFile] = []
        for path in self.iter_files():
            language = detect_language(path)
            if not language:
                continue
            try:
                parsed.append(self.parser.parse(path, root, language))
            except OSError:
                continue
        return parsed
