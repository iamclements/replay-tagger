"""Integration tests for Tagger using real ffmpeg/ffprobe.

These tests skip automatically when ffmpeg is not on PATH, so they are safe
to run in any environment. CI installs ffmpeg, so they always run there.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from replaytagger.tagger import Tagger

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_clip(path: Path) -> None:
    """Generate a 1-second silent black video at the given path using ffmpeg.

    The output container is determined by the file extension.
    """
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "color=black:size=16x16:rate=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
            "-y",
        ],
        check=True,
        capture_output=True,
    )


def _ffprobe_format(path: Path) -> dict:
    """Return the ffprobe format dict for the given file."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_entries",
            "format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout).get("format", {})


def _get_genre(path: Path) -> str | None:
    fmt = _ffprobe_format(path)
    # MKV stores tags in uppercase (GENRE); normalize to lowercase for comparison.
    tags = {k.lower(): v for k, v in fmt.get("tags", {}).items()}
    return tags.get("genre") or None


def _get_format_name(path: Path) -> str:
    return _ffprobe_format(path).get("format_name", "")


@pytest.fixture
def tagger() -> Tagger:
    return Tagger(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")


@pytest.fixture
def mp4_clip(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mp4"
    _make_clip(p)
    return p


@pytest.fixture
def mkv_clip(tmp_path: Path) -> Path:
    p = tmp_path / "clip.mkv"
    _make_clip(p)
    return p


# ---------------------------------------------------------------------------
# Genre tagging
# ---------------------------------------------------------------------------


class TestTagGenre:
    def test_mp4_genre_written(self, tagger: Tagger, mp4_clip: Path) -> None:
        result = tagger.tag(mp4_clip, "Apex Legends")
        assert result is True
        assert _get_genre(mp4_clip) == "Apex Legends"

    def test_mkv_genre_written(self, tagger: Tagger, mkv_clip: Path) -> None:
        result = tagger.tag(mkv_clip, "Cyberpunk 2077")
        assert result is True
        assert _get_genre(mkv_clip) == "Cyberpunk 2077"

    def test_skips_already_tagged(self, tagger: Tagger, mp4_clip: Path) -> None:
        tagger.tag(mp4_clip, "Apex Legends")
        result = tagger.tag(mp4_clip, "Apex Legends")
        assert result is False

    def test_force_retags(self, tagger: Tagger, mp4_clip: Path) -> None:
        tagger.tag(mp4_clip, "Apex Legends")
        result = tagger.tag(mp4_clip, "Hades", force=True)
        assert result is True
        assert _get_genre(mp4_clip) == "Hades"

    def test_dry_run_does_not_write(self, tagger: Tagger, mp4_clip: Path) -> None:
        result = tagger.tag(mp4_clip, "Apex Legends", dry_run=True)
        assert result is False
        assert _get_genre(mp4_clip) is None


# ---------------------------------------------------------------------------
# Container format preservation (the MKV remux bug regression test)
# ---------------------------------------------------------------------------


class TestContainerPreserved:
    def test_mp4_stays_mp4(self, tagger: Tagger, mp4_clip: Path) -> None:
        tagger.tag(mp4_clip, "Apex Legends")
        assert "mp4" in _get_format_name(mp4_clip)

    def test_mkv_stays_mkv(self, tagger: Tagger, mkv_clip: Path) -> None:
        tagger.tag(mkv_clip, "Cyberpunk 2077")
        assert "matroska" in _get_format_name(mkv_clip)


# ---------------------------------------------------------------------------
# Modification time preservation
# ---------------------------------------------------------------------------


class TestMtimePreserved:
    def test_mtime_restored_after_tag(self, tagger: Tagger, mp4_clip: Path) -> None:
        original_mtime = mp4_clip.stat().st_mtime
        tagger.tag(mp4_clip, "Apex Legends")
        assert abs(mp4_clip.stat().st_mtime - original_mtime) < 1.0

    def test_mtime_restored_after_mkv_tag(self, tagger: Tagger, mkv_clip: Path) -> None:
        original_mtime = mkv_clip.stat().st_mtime
        tagger.tag(mkv_clip, "Hades")
        assert abs(mkv_clip.stat().st_mtime - original_mtime) < 1.0
