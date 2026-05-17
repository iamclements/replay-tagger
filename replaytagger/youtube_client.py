from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = structlog.get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_API_SERVICE = "youtube"
YOUTUBE_API_VERSION = "v3"
_DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class YouTubeClient:
    """Handles OAuth2 authentication and video uploads to YouTube."""

    def __init__(self, credentials_file: Path, token_file: Path) -> None:
        self.credentials_file = credentials_file
        self.token_file = token_file
        self._service: Any = None

    def _device_flow(self) -> Credentials:
        """OAuth2 device flow — works in Docker/headless environments.

        Prints a URL and short code; the user enters the code at google.com/device.
        Credentials are sourced from YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET env vars
        (recommended for Docker) or from the credentials JSON file (local dev).
        Requires a 'TV and Limited Input devices' OAuth client in GCP.
        """
        client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")

        if not (client_id and client_secret):
            raw = json.loads(self.credentials_file.read_text())
            client_info: dict[str, str] = raw.get("installed") or raw.get("web") or {}
            if not client_info:
                raise ValueError(
                    "Unrecognised credentials file format — expected 'installed' or 'web' key.\n"
                    "Re-download from Google Cloud Console > APIs & Services > Credentials."
                )
            client_id = client_info["client_id"]
            client_secret = client_info["client_secret"]

        data = urllib.parse.urlencode({"client_id": client_id, "scope": " ".join(SCOPES)}).encode()
        with urllib.request.urlopen(urllib.request.Request(_DEVICE_CODE_URL, data=data)) as resp:
            code_resp: dict[str, Any] = json.loads(resp.read())

        device_code: str = code_resp["device_code"]
        user_code: str = code_resp["user_code"]
        verification_url: str = code_resp["verification_url"]
        expires_in: int = int(code_resp["expires_in"])
        interval: int = int(code_resp.get("interval", 5))

        print("\n" + "=" * 60)
        print("YouTube Authorization Required")
        print("=" * 60)
        print(f"  1. Open:  {verification_url}")
        print(f"  2. Enter: {user_code}")
        print("=" * 60)
        print(f"(Code expires in {expires_in // 60} minutes)\n")

        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            time.sleep(interval)
            token_data = urllib.parse.urlencode(
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "device_code": device_code,
                    "grant_type": _DEVICE_GRANT,
                }
            ).encode()
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(_TOKEN_URL, data=token_data)
                ) as resp:
                    token_resp: dict[str, Any] = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                body: dict[str, Any] = json.loads(exc.read())
                error = body.get("error", "")
                if error == "authorization_pending":
                    continue
                elif error == "slow_down":
                    interval += 5
                    continue
                elif error == "access_denied":
                    raise RuntimeError("YouTube authorization denied.")
                else:
                    raise RuntimeError(
                        f"OAuth2 error: {error} — {body.get('error_description', '')}"
                    )

            return Credentials(  # type: ignore[no-untyped-call]
                token=token_resp["access_token"],
                refresh_token=token_resp.get("refresh_token"),
                token_uri=_TOKEN_URL,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )

        raise RuntimeError("Authorization timed out — the code expired before it was entered.")

    def authenticate(self) -> None:
        """Run OAuth2 device flow on first run; refreshes token silently after."""
        creds: Credentials | None = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)  # type: ignore[no-untyped-call]

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())  # type: ignore[no-untyped-call]
            else:
                has_env_creds = bool(
                    os.environ.get("YOUTUBE_CLIENT_ID") and os.environ.get("YOUTUBE_CLIENT_SECRET")
                )
                if not has_env_creds and not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"YouTube credentials file not found: {self.credentials_file}\n"
                        "Either set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET env vars,\n"
                        "or download the credentials JSON from Google Cloud Console."
                    )
                creds = self._device_flow()

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(creds.to_json())  # type: ignore[no-untyped-call]
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
