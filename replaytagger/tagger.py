from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


def compute_content_hash(file_path: Path, max_bytes: int = 4 * 1024 * 1024) -> str:
    """SHA256 of the first max_bytes of a file; fast fingerprint for dedup."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        h.update(f.read(max_bytes))
    return h.hexdigest()


class Tagger:
    """Reads and writes genre metadata on video files using ffmpeg/ffprobe."""

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        temp_dir: Path | None = None,
    ) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.temp_dir = temp_dir
        self._validate_binaries()

    def _validate_binaries(self) -> None:
        for binary, attr in ((self.ffmpeg_path, "ffmpeg"), (self.ffprobe_path, "ffprobe")):
            if not shutil.which(binary):
                raise RuntimeError(
                    f"{attr} not found at '{binary}'. "
                    "Install ffmpeg or update the ffmpeg_path/ffprobe_path in config.yaml."
                )

    def get_genre(self, file_path: Path) -> str | None:
        """Returns the genre metadata value, or None if not set."""
        result = subprocess.run(
            [
                self.ffprobe_path,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_entries",
                "format_tags=genre",
                str(file_path),
            ],
            capture_output=True,
            text=True,
        )
        try:
            data = json.loads(result.stdout)
            return data.get("format", {}).get("tags", {}).get("genre") or None
        except (json.JSONDecodeError, AttributeError):
            return None

    def tag(
        self, file_path: Path, game_name: str, dry_run: bool = False, force: bool = False
    ) -> bool:
        """
        Writes game_name into the genre tag.

        Returns True if the file was modified, False if skipped or dry-run.
        Preserves the original file modification time after re-muxing.
        """
        bound = log.bind(file=file_path.name, game=game_name)

        if not force and self.get_genre(file_path) is not None:
            bound.debug("skipped", reason="genre_already_set")
            return False

        if dry_run:
            bound.info("dry_run", action="would_tag")
            return False

        original_mtime = file_path.stat().st_mtime

        # Write temp file to temp_dir if configured (keeps sync-tool-watched dirs clean),
        # otherwise write alongside the source file for an atomic rename.
        tmp_dir = self.temp_dir if self.temp_dir is not None else file_path.parent
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=f".tmp{file_path.suffix}", dir=tmp_dir)
        tmp_path = Path(tmp_name)
        os.close(tmp_fd)

        try:
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-i",
                    str(file_path),
                    "-metadata",
                    f"genre={game_name}",
                    "-codec",
                    "copy",
                    str(tmp_path),
                    "-y",
                ],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0 or not tmp_path.exists():
                bound.error("ffmpeg_failed", stderr=result.stderr[-500:])
                tmp_path.unlink(missing_ok=True)
                return False

            # Retry the replace on EBUSY (16) - a sync tool such as Syncthing may
            # briefly lock the temp file as it appears in the watched directory.
            for attempt in range(1, 4):
                try:
                    tmp_path.replace(file_path)
                    break
                except OSError as exc:
                    if exc.errno != 16 or attempt == 3:  # 16 = EBUSY
                        raise
                    bound.warning(
                        "replace_busy_retry",
                        attempt=attempt,
                        hint="set ffmpeg_temp_dir in config.yaml to a non-synced directory",
                    )
                    time.sleep(attempt * 2)

            os.utime(file_path, (original_mtime, original_mtime))
            bound.info("tagged")
            return True

        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
