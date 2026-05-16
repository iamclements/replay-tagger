from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

import structlog
from watchdog.events import FileCreatedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

log = structlog.get_logger(__name__)

FileCallback = Callable[[Path], None]


class _ClipEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        callback: FileCallback,
        extensions: list[str],
        debounce_seconds: int,
    ) -> None:
        super().__init__()
        self.callback = callback
        self.extensions = [e.lower() for e in extensions]
        self.debounce_seconds = debounce_seconds
        self._pending: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._schedule(str(event.src_path))

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if not event.is_directory:
            self._schedule(str(event.src_path))

    def _schedule(self, path: str) -> None:
        if not any(path.lower().endswith(ext) for ext in self.extensions):
            return
        with self._lock:
            existing = self._pending.pop(path, None)
            if existing:
                existing.cancel()
            timer = threading.Timer(self.debounce_seconds, self._fire, args=[path])
            self._pending[path] = timer
            timer.start()
        log.debug("watch_event_queued", path=Path(path).name, delay=self.debounce_seconds)

    def _fire(self, path: str) -> None:
        with self._lock:
            self._pending.pop(path, None)
        file_path = Path(path)
        if file_path.exists():
            self.callback(file_path)


def watch(
    clips_dir: Path,
    callback: FileCallback,
    extensions: list[str],
    debounce_seconds: int = 10,
) -> None:
    """
    Block indefinitely, calling callback(path) for each new/modified clip.
    The debounce delay lets Syncthing finish writing before processing.
    """
    handler = _ClipEventHandler(callback, extensions, debounce_seconds)
    observer = Observer()
    observer.schedule(handler, str(clips_dir), recursive=True)
    observer.start()
    log.info("watching", directory=str(clips_dir), debounce_seconds=debounce_seconds)

    try:
        while observer.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("watch_stopping")
    finally:
        observer.stop()
        observer.join()
