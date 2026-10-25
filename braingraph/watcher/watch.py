from __future__ import annotations

import time
from pathlib import Path
from threading import Timer
from time import monotonic

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from braingraph.config import BrainGraphConfig
from braingraph.parser.utils import detect_language, should_ignore
from braingraph.service import BrainGraphService


class DebouncedScanHandler(FileSystemEventHandler):
    def __init__(self, config: BrainGraphConfig, delay: float = 1.5) -> None:
        self.config = config
        self.delay = delay
        self.timer: Timer | None = None

    def on_any_event(self, event: FileSystemEvent) -> None:
        path = Path(event.src_path)
        if should_ignore(path, self.config.project_path, self.config.ignore_dirs):
            return
        if path.is_file() and not detect_language(path):
            return
        if self.timer:
            self.timer.cancel()
        self.timer = Timer(self.delay, self._scan)
        self.timer.daemon = True
        self.timer.start()

    def _scan(self) -> None:
        BrainGraphService(self.config.project_path).scan()


def watch_project(project_path: str | Path, duration_seconds: float | None = None) -> None:
    config = BrainGraphConfig.load(project_path)
    handler = DebouncedScanHandler(config)
    observer = Observer()
    observer.schedule(handler, str(config.project_path), recursive=True)
    observer.start()
    started = monotonic()
    try:
        while True:
            if duration_seconds is not None and (monotonic() - started) >= duration_seconds:
                break
            time.sleep(1)
    finally:
        observer.stop()
        observer.join()
