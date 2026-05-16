from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


class Tagger:
    """Reads and writes genre metadata on video files using ffmpeg/ffprobe."""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
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
                "-v", "quiet",
                "-print_format", "json",
                "-show_entries", "format_tags=genre",
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

    def tag(self, file_path: Path, game_name: str, dry_run: bool = False) -> bool:
        """
        Writes game_name into the genre tag.

        Returns True if the file was modified, False if skipped or dry-run.
        Preserves the original file modification time after re-muxing.
        """
        bound = log.bind(file=file_path.name, game=game_name)

        if self.get_genre(file_path) is not None:
            bound.debug("skipped", reason="genre_already_set")
            return False

        if dry_run:
            bound.info("dry_run", action="would_tag")
            return False

        original_mtime = file_path.stat().st_mtime

        # Write to a temp file in the same directory to allow atomic replace
        tmp_fd, tmp_name = tempfile.mkstemp(
            suffix=".tmp.mp4", dir=file_path.parent
        )
        tmp_path = Path(tmp_name)
        os.close(tmp_fd)

        try:
            result = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-i", str(file_path),
                    "-metadata", f"genre={game_name}",
                    "-codec", "copy",
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

            tmp_path.replace(file_path)
            os.utime(file_path, (original_mtime, original_mtime))
            bound.info("tagged")
            return True

        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
