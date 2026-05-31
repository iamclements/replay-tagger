from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from replaytagger.cli import main
from replaytagger.db import StateDB


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_config(tmp_path: Path, extra: dict | None = None) -> tuple[Path, Path, Path]:
    clips_dir = tmp_path / "clips"
    data_dir = tmp_path / "data"
    clips_dir.mkdir()
    data_dir.mkdir()
    data: dict = {
        "clips_dir": str(clips_dir),
        "data_dir": str(data_dir),
    }
    if extra:
        data.update(extra)
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return p, clips_dir, data_dir


def _fake_clip(clips_dir: Path, game: str = "Apex Legends") -> Path:
    game_dir = clips_dir / game
    game_dir.mkdir(exist_ok=True)
    clip = game_dir / "clip.mp4"
    clip.write_bytes(b"fake")
    return clip


# ── doctor ────────────────────────────────────────────────────────────────────


def test_doctor_passes_with_valid_setup(runner: CliRunner, tmp_path: Path) -> None:
    cfg, clips_dir, _ = _make_config(tmp_path)
    _fake_clip(clips_dir)
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        result = runner.invoke(main, ["--config", str(cfg), "doctor"])
    assert result.exit_code == 0
    assert "passed" in result.output


def test_doctor_fails_missing_clips_dir(runner: CliRunner, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    p = tmp_path / "config.yaml"
    p.write_text(
        yaml.dump(
            {
                "clips_dir": str(tmp_path / "missing"),
                "data_dir": str(data_dir),
            }
        )
    )
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        result = runner.invoke(main, ["--config", str(p), "doctor"])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_doctor_fails_missing_plex_token(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PLEX_TOKEN", raising=False)
    cfg, clips_dir, _ = _make_config(tmp_path, {"plex": {"enabled": True}})
    _fake_clip(clips_dir)
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        result = runner.invoke(main, ["--config", str(cfg), "doctor"])
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_doctor_skips_plex_when_disabled(runner: CliRunner, tmp_path: Path) -> None:
    cfg, _, _ = _make_config(tmp_path)
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        result = runner.invoke(main, ["--config", str(cfg), "doctor"])
    assert "SKIP" in result.output
    assert "plex" in result.output


# ── run ───────────────────────────────────────────────────────────────────────


def test_run_dry_run_no_modifications(runner: CliRunner, tmp_path: Path) -> None:
    cfg, clips_dir, data_dir = _make_config(tmp_path)
    _fake_clip(clips_dir)
    mock_tagger = MagicMock()
    mock_tagger.tag.return_value = False
    with patch("replaytagger.cli.Tagger", return_value=mock_tagger):
        result = runner.invoke(main, ["--config", str(cfg), "--dry-run", "run"])
    assert result.exit_code == 0
    assert StateDB(data_dir / "state.db").stats()["total_tagged"] == 0


def test_run_force_reprocesses_tagged_files(runner: CliRunner, tmp_path: Path) -> None:
    cfg, clips_dir, data_dir = _make_config(tmp_path)
    clip = _fake_clip(clips_dir)
    db = StateDB(data_dir / "state.db")
    db.mark_tagged(clip, "Apex Legends", "abc123")
    mock_tagger = MagicMock()
    mock_tagger.tag.return_value = True
    with patch("replaytagger.cli.Tagger", return_value=mock_tagger):
        result = runner.invoke(main, ["--config", str(cfg), "run", "--force"])
    assert result.exit_code == 0
    mock_tagger.tag.assert_called_once()


# ── retag ─────────────────────────────────────────────────────────────────────


def test_retag_single_file(runner: CliRunner, tmp_path: Path) -> None:
    cfg, clips_dir, data_dir = _make_config(tmp_path)
    clip = _fake_clip(clips_dir)
    mock_tagger = MagicMock()
    mock_tagger.tag.return_value = True
    with patch("replaytagger.cli.Tagger", return_value=mock_tagger):
        result = runner.invoke(main, ["--config", str(cfg), "retag", str(clip)])
    assert result.exit_code == 0
    assert "Retagged" in result.output
    assert StateDB(data_dir / "state.db").stats()["total_tagged"] == 1


def test_retag_dry_run(runner: CliRunner, tmp_path: Path) -> None:
    cfg, clips_dir, _ = _make_config(tmp_path)
    clip = _fake_clip(clips_dir)
    mock_tagger = MagicMock()
    mock_tagger.tag.return_value = False
    with patch("replaytagger.cli.Tagger", return_value=mock_tagger):
        result = runner.invoke(main, ["--config", str(cfg), "--dry-run", "retag", str(clip)])
    assert result.exit_code == 0
    assert "Would retag" in result.output
    mock_tagger.tag.assert_called_once_with(clip, "Apex Legends", dry_run=True, force=True)


# ── status ────────────────────────────────────────────────────────────────────


def test_status_empty_db(runner: CliRunner, tmp_path: Path) -> None:
    cfg, _, _ = _make_config(tmp_path)
    result = runner.invoke(main, ["--config", str(cfg), "status"])
    assert result.exit_code == 0
    assert "Tagged clips : 0" in result.output


# ── health ────────────────────────────────────────────────────────────────────


def test_health_fresh_heartbeat(runner: CliRunner, tmp_path: Path) -> None:
    cfg, _, data_dir = _make_config(tmp_path)
    (data_dir / ".health").write_text("ok")
    result = runner.invoke(main, ["--config", str(cfg), "health"])
    assert result.exit_code == 0


def test_health_stale_heartbeat(runner: CliRunner, tmp_path: Path) -> None:
    cfg, _, data_dir = _make_config(tmp_path)
    health_file = data_dir / ".health"
    health_file.write_text("ok")
    stale = time.time() - 200
    os.utime(health_file, (stale, stale))
    result = runner.invoke(main, ["--config", str(cfg), "health"])
    assert result.exit_code == 1
