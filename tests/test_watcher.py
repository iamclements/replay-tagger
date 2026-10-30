from __future__ import annotations

import threading
import time
from pathlib import Path

from replaytagger.watcher import watch


def test_polling_mode_detects_new_clip(tmp_path: Path) -> None:
    seen: list[Path] = []
    event = threading.Event()

    def callback(path: Path) -> None:
        seen.append(path)
        event.set()

    t = threading.Thread(
        target=watch,
        args=(tmp_path, callback, [".mp4"]),
        kwargs={"debounce_seconds": 1, "poll_interval_seconds": 1},
        daemon=True,
    )
    t.start()
    time.sleep(1.5)
    clip = tmp_path / "Game" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"x" * 10)

    assert event.wait(timeout=15)
    assert clip in seen
