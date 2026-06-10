from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date, datetime
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

    _SIZE_POLL_INTERVAL = 2  # seconds between size samples

    def _fire(self, path: str) -> None:
        with self._lock:
            self._pending.pop(path, None)
        file_path = Path(path)
        if not file_path.exists():
            return
        try:
            size_before = file_path.stat().st_size
            time.sleep(self._SIZE_POLL_INTERVAL)
            if not file_path.exists():
                return
            size_after = file_path.stat().st_size
        except OSError:
            return
        if size_before != size_after:
            log.debug(
                "watch_file_still_growing",
                path=file_path.name,
                before=size_before,
                after=size_after,
                action="requeue",
            )
            self._schedule(path)
            return
        self.callback(file_path)


def watch(
    clips_dir: Path,
    callback: FileCallback,
    extensions: list[str],
    debounce_seconds: int = 10,
    heartbeat_path: Path | None = None,
    on_daily_sync: Callable[[], None] | None = None,
    daily_sync_hour: int = 3,
) -> None:
    """
    Block indefinitely, calling callback(path) for each new/modified clip.
    The debounce delay lets Syncthing finish writing before processing.
    If heartbeat_path is provided, touches it on start and every 30 seconds
    so Docker HEALTHCHECK can verify the watcher is alive.
    If on_daily_sync is provided, it is called once per calendar day when the
    local hour reaches daily_sync_hour (0-23). Used to retry YouTube uploads
    after a quota reset.
    """
    handler = _ClipEventHandler(callback, extensions, debounce_seconds)
    observer = Observer()
    observer.schedule(handler, str(clips_dir), recursive=True)
    observer.start()
    log.info("watching", directory=str(clips_dir), debounce_seconds=debounce_seconds)

    if heartbeat_path:
        heartbeat_path.touch()

    last_sync_date: date | None = None

    try:
        tick = 0
        while observer.is_alive():
            time.sleep(1)
            tick += 1
            if heartbeat_path and tick % 30 == 0:
                heartbeat_path.touch()
            if on_daily_sync is not None:
                now = datetime.now()
                today = now.date()
                if last_sync_date != today and now.hour >= daily_sync_hour:
                    last_sync_date = today
                    try:
                        on_daily_sync()
                    except Exception:
                        log.exception("daily_sync_error")
    except KeyboardInterrupt:
        log.info("watch_stopping")
    finally:
        observer.stop()
        observer.join()
