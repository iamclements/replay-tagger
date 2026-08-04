from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from replaytagger.tagger import Tagger


@pytest.fixture
def tagger() -> Tagger:
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        return Tagger(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")


def _ffprobe_result(genre: str | None) -> MagicMock:
    tags = {"genre": genre} if genre else {}
    payload = json.dumps({"format": {"tags": tags}})
    return MagicMock(stdout=payload, returncode=0)


def test_get_genre_returns_none_when_not_set(tagger: Tagger) -> None:
    with patch("subprocess.run", return_value=_ffprobe_result(None)):
        assert tagger.get_genre(Path("clip.mp4")) is None


def test_get_genre_returns_value_when_set(tagger: Tagger) -> None:
    with patch("subprocess.run", return_value=_ffprobe_result("Apex Legends")):
        assert tagger.get_genre(Path("clip.mp4")) == "Apex Legends"


def test_get_genre_handles_malformed_json(tagger: Tagger) -> None:
    bad = MagicMock(stdout="not json", returncode=0)
    with patch("subprocess.run", return_value=bad):
        assert tagger.get_genre(Path("clip.mp4")) is None


def test_tag_skips_file_with_existing_genre(tagger: Tagger, tmp_path: Path) -> None:
    clip = tmp_path / "Apex Legends" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"fake")

    with patch.object(tagger, "get_genre", return_value="Apex Legends"):
        result = tagger.tag(clip, "Apex Legends")

    assert result is False


def test_tag_dry_run_does_not_call_ffmpeg(tagger: Tagger, tmp_path: Path) -> None:
    clip = tmp_path / "Apex Legends" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"fake")

    with patch.object(tagger, "get_genre", return_value=None):
        with patch("subprocess.run") as mock_run:
            result = tagger.tag(clip, "Apex Legends", dry_run=True)

    assert result is False
    mock_run.assert_not_called()


def test_tag_returns_false_when_ffmpeg_fails(tagger: Tagger, tmp_path: Path) -> None:
    clip = tmp_path / "Apex Legends" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"fake")

    failed = MagicMock(returncode=1, stderr="some ffmpeg error")

    with patch.object(tagger, "get_genre", return_value=None):
        with patch("subprocess.run", return_value=failed):
            # Temp file won't be created, so tag() returns False
            result = tagger.tag(clip, "Apex Legends")

    assert result is False


def test_tagger_raises_if_ffmpeg_missing() -> None:
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="ffmpeg not found"):
            Tagger()


def test_tag_force_overwrites_existing_genre(tagger: Tagger, tmp_path: Path) -> None:
    clip = tmp_path / "Apex Legends" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"fake")

    succeeded = MagicMock(returncode=0, stderr="")

    with patch.object(tagger, "get_genre", return_value="Old Game"):
        with patch("subprocess.run", return_value=succeeded):
            with patch("replaytagger.tagger.Path.replace"):
                with patch("os.utime"):
                    # tmp file needs to appear to exist for tag() to proceed
                    with patch("pathlib.Path.exists", return_value=True):
                        result = tagger.tag(clip, "Apex Legends", force=True)

    assert result is True


def test_tag_skips_existing_genre_without_force(tagger: Tagger, tmp_path: Path) -> None:
    clip = tmp_path / "Apex Legends" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"fake")

    with patch.object(tagger, "get_genre", return_value="Apex Legends"):
        result = tagger.tag(clip, "Apex Legends", force=False)

    assert result is False


def test_tag_retags_mismatched_genre_without_force(tagger: Tagger, tmp_path: Path) -> None:
    clip = tmp_path / "Apex Legends" / "clip.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"fake")

    succeeded = MagicMock(returncode=0, stderr="")

    with patch.object(tagger, "get_genre", return_value="Old Game"):
        with patch("subprocess.run", return_value=succeeded):
            with patch("replaytagger.tagger.Path.replace"):
                with patch("os.utime"):
                    with patch("pathlib.Path.exists", return_value=True):
                        result = tagger.tag(clip, "Apex Legends", force=False)

    assert result is True
