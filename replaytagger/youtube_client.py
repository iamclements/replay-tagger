from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import structlog
from google.auth.exceptions import RefreshError
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

    def _load_client_credentials(self) -> tuple[str, str]:
        """Return (client_id, client_secret) from env vars or credentials file."""
        client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
        if client_id and client_secret:
            return client_id, client_secret

        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"YouTube credentials file not found: {self.credentials_file}\n"
                "Either set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET env vars,\n"
                "or download the credentials JSON from Google Cloud Console."
            )
        raw = json.loads(self.credentials_file.read_text())
        client_info: dict[str, str] = raw.get("installed") or raw.get("web") or {}
        if not client_info:
            raise ValueError(
                "Unrecognised credentials file format; expected 'installed' or 'web' key.\n"
                "Re-download from Google Cloud Console > APIs & Services > Credentials."
            )
        return client_info["client_id"], client_info["client_secret"]

    def _device_flow(self) -> Credentials:
        """OAuth2 device flow for Docker/headless environments.

        Prints a URL and short code; the user enters the code at google.com/device.
        Requires a 'TV and Limited Input devices' OAuth client in GCP.
        """
        client_id, client_secret = self._load_client_credentials()

        data = urllib.parse.urlencode({"client_id": client_id, "scope": " ".join(SCOPES)}).encode()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(_DEVICE_CODE_URL, data=data)
            ) as resp:
                code_resp: dict[str, Any] = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_bytes = exc.read()
            try:
                body = json.loads(body_bytes)
                error_desc = body.get("error_description", "")
            except Exception:
                error_desc = body_bytes.decode(errors="replace")

            if exc.code == 400:
                raise RuntimeError(
                    "Google rejected the device authorization request (HTTP 400).\n\n"
                    "Most common cause: the OAuth client in Google Cloud Console is not\n"
                    "set to 'TV and Limited Input devices'.\n\n"
                    "To fix:\n"
                    "  1. Open Google Cloud Console > APIs & Services > Credentials\n"
                    "  2. Delete the current OAuth client\n"
                    "  3. Create a new one: type = 'TV and Limited Input devices'\n"
                    "  4. Update YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env\n"
                    f"  5. Run: docker compose run --rm replaytagger youtube-auth\n\n"
                    f"Google error: {error_desc}"
                ) from exc
            raise RuntimeError(
                f"Failed to start YouTube device authorization (HTTP {exc.code}): {error_desc}"
            ) from exc

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
                poll_body: dict[str, Any] = json.loads(exc.read())
                error = poll_body.get("error", "")
                if error == "authorization_pending":
                    continue
                elif error == "slow_down":
                    interval += 5
                    continue
                elif error == "access_denied":
                    raise RuntimeError("YouTube authorization denied.")
                else:
                    raise RuntimeError(
                        f"OAuth2 error: {error}: {poll_body.get('error_description', '')}"
                    )

            return Credentials(  # type: ignore[no-untyped-call]
                token=token_resp["access_token"],
                refresh_token=token_resp.get("refresh_token"),
                token_uri=_TOKEN_URL,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )

        raise RuntimeError("Authorization timed out; the code expired before it was entered.")

    def authenticate(self) -> None:
        """Load token from file and refresh if needed; runs device flow if no valid token exists.

        If the token file exists but has no refresh_token (Google omits it on
        re-authorization), the previous refresh_token is carried over so that
        subsequent expiry cycles can still refresh silently.
        """
        creds: Credentials | None = None
        existing_refresh_token: str | None = None

        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
                    str(self.token_file), SCOPES
                )
                # Preserve the refresh token in case a re-auth doesn't re-issue one.
                existing_refresh_token = creds.refresh_token
            except Exception as exc:
                log.warning("youtube_token_load_failed", error=str(exc))
                creds = None

        if creds and creds.valid:
            log.debug("youtube_token_valid")
        elif creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())  # type: ignore[no-untyped-call]
                log.info("youtube_token_refreshed")
            except RefreshError as exc:
                log.warning(
                    "youtube_token_refresh_failed",
                    error=str(exc),
                    action="re-running device authorization flow",
                )
                creds = self._device_flow()
        else:
            if creds and creds.expired and not creds.refresh_token:
                log.warning(
                    "youtube_token_no_refresh_token",
                    action="re-running device authorization flow",
                    hint=(
                        "If this happens repeatedly, delete data/youtube_token.json "
                        "and run youtube-auth again"
                    ),
                )
            creds = self._device_flow()

        # If the new credentials are missing a refresh_token (Google doesn't always
        # re-issue one), carry over the token from the previous session.
        if creds.refresh_token is None and existing_refresh_token:
            creds = Credentials(  # type: ignore[no-untyped-call]
                token=creds.token,
                refresh_token=existing_refresh_token,
                token_uri=creds.token_uri,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=creds.scopes,
            )
            log.debug("youtube_refresh_token_carried_over")

        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(creds.to_json())  # type: ignore[no-untyped-call]
        log.info("youtube_token_saved", path=str(self.token_file))

        self._service = build(YOUTUBE_API_SERVICE, YOUTUBE_API_VERSION, credentials=creds)
        log.info("youtube_authenticated")

    def upload(
        self,
        file_path: Path,
        game_name: str,
        privacy: str = "private",
    ) -> str:
        """Upload a clip to YouTube. Returns the YouTube video ID."""
        if self._service is None:
            self.authenticate()

        body = {
            "snippet": {
                "title": file_path.stem,
                "description": f"Game clip from {game_name}.",
                "tags": [game_name, "gaming", "clips"],
                "categoryId": "20",  # Gaming
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(file_path),
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
