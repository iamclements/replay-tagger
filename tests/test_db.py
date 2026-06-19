from __future__ import annotations

from pathlib import Path

import pytest

from replaytagger.db import StateDB


@pytest.fixture
def db(tmp_path: Path) -> StateDB:
    return StateDB(tmp_path / "state.db")


@pytest.fixture
def clip(tmp_path: Path) -> Path:
    p = tmp_path / "Apex Legends" / "clip.mp4"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"fake video data")
    return p


def test_is_tagged_false_for_unknown_file(db: StateDB, clip: Path) -> None:
    assert db.is_tagged(clip) is False


def test_mark_then_is_tagged(db: StateDB, clip: Path) -> None:
    db.mark_tagged(clip, "Apex Legends")
    assert db.is_tagged(clip) is True


def test_is_tagged_false_after_file_content_changes(db: StateDB, clip: Path) -> None:
    db.mark_tagged(clip, "Apex Legends")
    # Simulate the file being replaced (new size)
    clip.write_bytes(b"completely different video data with more bytes")
    assert db.is_tagged(clip) is False


def test_is_tagged_false_for_missing_file(db: StateDB, tmp_path: Path) -> None:
    ghost = tmp_path / "ghost.mp4"
    assert db.is_tagged(ghost) is False


def test_mark_uploaded_and_get_youtube_id(db: StateDB, clip: Path) -> None:
    db.mark_tagged(clip, "Apex Legends")
    assert db.get_youtube_id(clip) is None

    db.mark_uploaded(clip, "dQw4w9WgXcQ")
    assert db.get_youtube_id(clip) == "dQw4w9WgXcQ"


def test_stats_counts_correctly(db: StateDB, tmp_path: Path) -> None:
    for i in range(3):
        p = tmp_path / f"clip{i}.mp4"
        p.write_bytes(b"data" * i)
        db.mark_tagged(p, "Game")

    db.mark_uploaded(tmp_path / "clip1.mp4", f"vid_{1}")

    stats = db.stats()
    assert stats["total_tagged"] == 3
    assert stats["total_uploaded"] == 1


def test_pending_uploads_counts_unuploaded(db: StateDB, clip: Path) -> None:
    db.mark_tagged(clip, "Apex Legends")
    assert db.pending_uploads(0) == 1
    db.mark_uploaded(clip, "vid123")
    assert db.pending_uploads(0) == 0


def test_pending_uploads_defers_recent_clips(db: StateDB, clip: Path) -> None:
    db.mark_tagged(clip, "Apex Legends")
    # Just-tagged clip is younger than the 7-day window, so it is not pending yet.
    assert db.pending_uploads(7) == 0


def test_last_tagged_returns_none_when_empty(db: StateDB) -> None:
    assert db.last_tagged() is None


def test_last_tagged_returns_most_recent(db: StateDB, tmp_path: Path) -> None:
    for i in range(3):
        p = tmp_path / f"clip{i}.mp4"
        p.write_bytes(b"data" * (i + 1))
        db.mark_tagged(p, f"Game{i}")

    last = db.last_tagged()
    assert last is not None
    assert last["game_name"] == "Game2"


def test_clear_tagged_removes_record(db: StateDB, clip: Path) -> None:
    db.mark_tagged(clip, "Apex Legends")
    assert db.is_tagged(clip) is True
    db.clear_tagged(clip)
    assert db.is_tagged(clip) is False
