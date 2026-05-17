from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PlexConfig:
    enabled: bool = False
    url: str = "http://localhost:32400"
    token: str = field(default="", repr=False)
    library_name: str = "Game Clips"
    auto_scan: bool = True
    auto_create_collections: bool = True
    verify_ssl: bool = True


@dataclass
class YouTubeConfig:
    enabled: bool = False
    auto_upload: bool = False
    privacy: str = "private"
    compress: bool = True
    resolution: int = 1080
    crf: int = 28
    upload_after_days: int = 0
    credentials_file: Path = Path("youtube_credentials.json")
    token_file: Path = Path("data/youtube_token.json")


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "json"


@dataclass
class AppConfig:
    clips_dir: Path = Path("/clips")
    extensions: list[str] = field(default_factory=lambda: [".mp4", ".mkv", ".mov"])
    data_dir: Path = Path("data")
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    debounce_seconds: int = 10
    plex: PlexConfig = field(default_factory=PlexConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(config_path: Path) -> AppConfig:
    data: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

    plex_data = data.get("plex", {})
    youtube_data = data.get("youtube", {})
    logging_data = data.get("logging", {})

    # Environment variables override config file values — secrets never go in config.yaml
    clips_dir = Path(os.environ.get("CLIPS_DIR", data.get("clips_dir", "/clips")))
    data_dir = Path(os.environ.get("DATA_DIR", data.get("data_dir", "data")))
    plex_url = os.environ.get("PLEX_URL", plex_data.get("url", "http://localhost:32400"))
    _verify_ssl_env = os.environ.get("PLEX_VERIFY_SSL", "").lower()
    plex_verify_ssl = False if _verify_ssl_env == "false" else plex_data.get("verify_ssl", True)

    # Token priority: PLEX_TOKEN env var → config.yaml → token file saved by plex-auth
    plex_token = os.environ.get("PLEX_TOKEN", plex_data.get("token", ""))
    if not plex_token:
        _token_file = data_dir / "plex_token"
        if _token_file.exists():
            plex_token = _token_file.read_text().strip()
    log_level = os.environ.get("LOG_LEVEL", logging_data.get("level", "INFO"))
    log_format = os.environ.get("LOG_FORMAT", logging_data.get("format", "json"))

    plex = PlexConfig(
        enabled=plex_data.get("enabled", False),
        url=plex_url,
        token=plex_token,
        library_name=plex_data.get("library_name", "Game Clips"),
        auto_scan=plex_data.get("auto_scan", True),
        auto_create_collections=plex_data.get("auto_create_collections", True),
        verify_ssl=plex_verify_ssl,
    )

    yt_credentials = youtube_data.get("credentials_file", "youtube_credentials.json")
    yt_token = youtube_data.get("token_file", "data/youtube_token.json")
    yt_upload_after_days = int(
        os.environ.get(
            "YOUTUBE_UPLOAD_AFTER_DAYS",
            youtube_data.get("upload_after_days", 0),
        )
    )

    _yt_enabled_env = os.environ.get("YOUTUBE_ENABLED", "").lower()
    yt_enabled = (
        True
        if _yt_enabled_env == "true"
        else False
        if _yt_enabled_env == "false"
        else youtube_data.get("enabled", False)
    )

    youtube = YouTubeConfig(
        enabled=yt_enabled,
        auto_upload=youtube_data.get("auto_upload", False),
        privacy=os.environ.get("YOUTUBE_PRIVACY", youtube_data.get("privacy", "private")),
        compress=youtube_data.get("compress", True),
        resolution=youtube_data.get("resolution", 1080),
        crf=youtube_data.get("crf", 28),
        upload_after_days=yt_upload_after_days,
        credentials_file=Path(yt_credentials),
        token_file=Path(yt_token),
    )

    return AppConfig(
        clips_dir=clips_dir,
        extensions=data.get("extensions", [".mp4", ".mkv", ".mov"]),
        data_dir=data_dir,
        ffmpeg_path=data.get("ffmpeg_path", "ffmpeg"),
        ffprobe_path=data.get("ffprobe_path", "ffprobe"),
        debounce_seconds=data.get("debounce_seconds", 10),
        plex=plex,
        youtube=youtube,
        logging=LoggingConfig(level=log_level, format=log_format),
    )
