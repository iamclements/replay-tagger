from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from replaytagger.config import load_config


def _write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return p


def test_defaults_when_no_config_file(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.extensions == [".mp4", ".mkv", ".mov"]
    assert cfg.plex.enabled is False
    assert cfg.youtube.enabled is False


def test_loads_clips_dir_from_file(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {"clips_dir": "/mnt/nas/clips"})
    cfg = load_config(p)
    assert cfg.clips_dir == Path("/mnt/nas/clips")


def test_plex_token_from_env_overrides_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_config(tmp_path, {"plex": {"enabled": True, "token": "from_file"}})
    monkeypatch.setenv("PLEX_TOKEN", "from_env")
    cfg = load_config(p)
    assert cfg.plex.token == "from_env"


def test_plex_url_from_env_overrides_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_config(tmp_path, {"plex": {"url": "http://file-host:32400"}})
    monkeypatch.setenv("PLEX_URL", "http://env-host:32400")
    cfg = load_config(p)
    assert cfg.plex.url == "http://env-host:32400"


def test_log_level_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_config(tmp_path, {})
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    cfg = load_config(p)
    assert cfg.logging.level == "DEBUG"


def test_youtube_privacy_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write_config(tmp_path, {"youtube": {"enabled": True}})
    monkeypatch.setenv("YOUTUBE_PRIVACY", "public")
    cfg = load_config(p)
    assert cfg.youtube.privacy == "public"


def test_extensions_loaded_from_config(tmp_path: Path) -> None:
    p = _write_config(tmp_path, {"extensions": [".mp4", ".avi"]})
    cfg = load_config(p)
    assert cfg.extensions == [".mp4", ".avi"]
