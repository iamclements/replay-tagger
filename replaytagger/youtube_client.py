from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = structlog.get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"


class YouTubeClient:
    """Handles OAuth2 authentication and video uploads to YouTube."""

    def __init__(self, credentials_file: Path, token_file: Path) -> None:
        self.credentials_file = credentials_file
        self.token_file = token_file
        self._service: Any = None

    def authenticate(self) -> None:
        """Run OAuth2 flow. Opens a browser on first run; refreshes silently after."""
        creds: Credentials | None = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)  # type: ignore[no-untyped-call]

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())  # type: ignore[no-untyped-call]
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"YouTube credentials file not found: {self.credentials_file}\n"
                        "Download it from Google Cloud Console > APIs & Services > Credentials."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_file), SCOPES)
                creds = flow.run_local_server(port=0)

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json())
            log.info("youtube_token_saved", path=str(self.token_file))

        self._service = build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, credentials=creds)
        log.info("youtube_authenticated")

    def compress(
        self,
        input_path: Path,
        ffmpeg_path: str = "ffmpeg",
        resolution: int = 1080,
        crf: int = 28,
    ) -> Path:
        """Re-encode to H.264 for smaller upload size. Returns path to temp file."""
        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".compressed.mp4")
        output_path = Path(tmp_name)
        import os

        os.close(tmp_fd)

        log.info("compressing", file=input_path.name, resolution=resolution, crf=crf)
        result = subprocess.run(
            [
                ffmpeg_path,
                "-i",
                str(input_path),
                "-c:v",
                "libx264",
                "-crf",
                str(crf),
                "-preset",
                "fast",
                "-vf",
                f"scale=-2:{resolution}",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output_path),
                "-y",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(f"Compression failed: {result.stderr[-500:]}")

        return output_path

    def upload(
        self,
        file_path: Path,
        game_name: str,
        privacy: str = "private",
        compress: bool = True,
        ffmpeg_path: str = "ffmpeg",
        resolution: int = 1080,
        crf: int = 28,
    ) -> str:
        """
        Upload a clip to YouTube.

        Returns the YouTube video ID.
        Compresses the file first if compress=True.
        """
        if self._service is None:
            self.authenticate()

        upload_path = file_path
        tmp_path: Path | None = None

        try:
            if compress:
                tmp_path = self.compress(file_path, ffmpeg_path, resolution, crf)
                upload_path = tmp_path

            body = {
                "snippet": {
                    "title": file_path.stem,
                    "description": f"Game clip from {game_name}.",
                    "tags": [game_name, "gaming", "clips", "NVIDIA"],
                    "categoryId": "20",  # Gaming
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": False,
                },
            }

            media = MediaFileUpload(
                str(upload_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=10 * 1024 * 1024,  # 10 MB chunks
            )

            log.info("uploading", file=file_path.name, privacy=privacy)
            request = self._service.videos().insert(
                part=",".join(body.keys()), body=body, media_body=media
            )

            response = None
            while response is None:
                _, response = request.next_chunk()

            video_id: str = response["id"]
            log.info("uploaded", file=file_path.name, video_id=video_id)
            return video_id

        finally:
            if tmp_path:
                tmp_path.unlink(missing_ok=True)
