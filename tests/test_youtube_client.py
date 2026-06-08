from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.auth.exceptions import RefreshError

from replaytagger.youtube_client import YouTubeClient, YouTubeQuotaExceededError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(tmp_path: Path, token: dict | None = None) -> YouTubeClient:
    creds_file = tmp_path / "credentials.json"
    creds_file.write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "csec"}}))
    token_file = tmp_path / "token.json"
    if token is not None:
        token_file.write_text(json.dumps(token))
    return YouTubeClient(credentials_file=creds_file, token_file=token_file)


def _http_error(code: int, body: dict) -> urllib.error.HTTPError:
    import io

    encoded = json.dumps(body).encode()
    return urllib.error.HTTPError(
        url="https://example.com",
        code=code,
        msg=str(code),
        hdrs={},  # type: ignore[arg-type]
        fp=io.BytesIO(encoded),
    )


def _fake_creds(
    valid: bool = True,
    expired: bool = False,
    refresh_token: str | None = "rtoken",
) -> MagicMock:
    c = MagicMock(
        spec=[
            "valid",
            "expired",
            "refresh_token",
            "token",
            "token_uri",
            "client_id",
            "client_secret",
            "scopes",
            "to_json",
            "refresh",
        ]
    )
    c.valid = valid
    c.expired = expired
    c.refresh_token = refresh_token
    c.token = "atoken"
    c.token_uri = "https://oauth2.googleapis.com/token"
    c.client_id = "cid"
    c.client_secret = "csec"
    c.scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    c.to_json.return_value = json.dumps({"token": "atoken", "refresh_token": refresh_token})
    return c


# ---------------------------------------------------------------------------
# _device_flow: HTTP 400 from device code endpoint
# ---------------------------------------------------------------------------


class TestDeviceFlow400:
    def test_raises_runtime_error_with_actionable_message(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        err = _http_error(400, {"error": "invalid_client", "error_description": "bad client"})

        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError) as exc_info:
                client._device_flow()

        msg = str(exc_info.value)
        assert "HTTP 400" in msg
        assert "TV and Limited Input devices" in msg
        assert "Google Cloud Console" in msg
        assert "youtube-auth" in msg

    def test_non_400_error_re_raises_without_client_type_hint(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        err = _http_error(500, {"error": "server_error", "error_description": "oops"})

        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError) as exc_info:
                client._device_flow()

        msg = str(exc_info.value)
        assert "HTTP 400" not in msg
        assert "TV and Limited Input devices" not in msg
        assert "500" in msg


# ---------------------------------------------------------------------------
# authenticate: RefreshError fallback to device flow
# ---------------------------------------------------------------------------


class TestAuthenticateRefreshFallback:
    def test_refresh_error_falls_back_to_device_flow(self, tmp_path: Path) -> None:
        """RefreshError must fall back to device flow rather than crashing."""
        expired_creds = _fake_creds(valid=False, expired=True, refresh_token="old_rtoken")
        new_creds = _fake_creds(valid=True, expired=False, refresh_token="new_rtoken")
        # Token file must exist so the load path is taken
        client = _make_client(tmp_path, token={"token": "t", "refresh_token": "old_rtoken"})

        with (
            patch(
                "replaytagger.youtube_client.Credentials.from_authorized_user_file",
                return_value=expired_creds,
            ),
            patch.object(expired_creds, "refresh", side_effect=RefreshError("token revoked")),
            patch.object(client, "_device_flow", return_value=new_creds) as mock_flow,
            patch("replaytagger.youtube_client.build"),
        ):
            client.authenticate()

        mock_flow.assert_called_once()

    def test_valid_token_skips_device_flow(self, tmp_path: Path) -> None:
        """A valid token should authenticate without triggering device flow."""
        valid_creds = _fake_creds(valid=True, expired=False)
        client = _make_client(tmp_path, token={"token": "t", "refresh_token": "rtoken"})

        with (
            patch(
                "replaytagger.youtube_client.Credentials.from_authorized_user_file",
                return_value=valid_creds,
            ),
            patch.object(client, "_device_flow") as mock_flow,
            patch("replaytagger.youtube_client.build"),
        ):
            client.authenticate()

        mock_flow.assert_not_called()

    def test_expired_token_with_refresh_token_tries_refresh_first(self, tmp_path: Path) -> None:
        """Expired token with a refresh_token should attempt refresh before device flow."""
        expired_creds = _fake_creds(valid=False, expired=True, refresh_token="rtoken")
        client = _make_client(tmp_path, token={"token": "t", "refresh_token": "rtoken"})

        with (
            patch(
                "replaytagger.youtube_client.Credentials.from_authorized_user_file",
                return_value=expired_creds,
            ),
            patch.object(expired_creds, "refresh") as mock_refresh,
            patch.object(client, "_device_flow") as mock_flow,
            patch("replaytagger.youtube_client.build"),
        ):
            # Simulate successful refresh by making creds look valid afterwards
            def do_refresh(_req: object) -> None:
                expired_creds.valid = True
                expired_creds.expired = False

            mock_refresh.side_effect = do_refresh
            client.authenticate()

        mock_refresh.assert_called_once()
        mock_flow.assert_not_called()


# ---------------------------------------------------------------------------
# authenticate: refresh token carry-over
# ---------------------------------------------------------------------------


class TestRefreshTokenCarryOver:
    def test_missing_refresh_token_carried_over_in_saved_file(self, tmp_path: Path) -> None:
        """If device flow returns credentials without a refresh_token, the saved token
        file must still contain the previous refresh_token so the next refresh works."""
        old_creds = _fake_creds(valid=False, expired=True, refresh_token="previous_rtoken")
        # New credentials from device flow - Google omitted refresh_token
        new_creds_no_refresh = _fake_creds(valid=True, expired=False, refresh_token=None)

        client = _make_client(tmp_path, token={"token": "t", "refresh_token": "previous_rtoken"})

        with (
            patch(
                "replaytagger.youtube_client.Credentials.from_authorized_user_file",
                return_value=old_creds,
            ),
            patch.object(old_creds, "refresh", side_effect=RefreshError("revoked")),
            patch.object(client, "_device_flow", return_value=new_creds_no_refresh),
            patch("replaytagger.youtube_client.build"),
        ):
            client.authenticate()

        # The saved token file must contain the carried-over refresh_token
        saved = json.loads(client.token_file.read_text())
        assert saved.get("refresh_token") == "previous_rtoken"

    def test_new_creds_with_refresh_token_saved_as_is(self, tmp_path: Path) -> None:
        """If device flow returns a new refresh_token, it is saved without modification."""
        old_creds = _fake_creds(valid=False, expired=True, refresh_token="old_rtoken")
        new_creds_with_refresh = _fake_creds(valid=True, expired=False, refresh_token="new_rtoken")

        client = _make_client(tmp_path, token={"token": "t", "refresh_token": "old_rtoken"})

        with (
            patch(
                "replaytagger.youtube_client.Credentials.from_authorized_user_file",
                return_value=old_creds,
            ),
            patch.object(old_creds, "refresh", side_effect=RefreshError("revoked")),
            patch.object(client, "_device_flow", return_value=new_creds_with_refresh),
            patch("replaytagger.youtube_client.build"),
        ):
            client.authenticate()

        saved = json.loads(client.token_file.read_text())
        assert saved.get("refresh_token") == "new_rtoken"


# ---------------------------------------------------------------------------
# NVIDIA tag removed from uploads
# ---------------------------------------------------------------------------


class TestUploadQuota:
    def _make_http_error(self, status: int, reason: str) -> MagicMock:
        from googleapiclient.errors import HttpError

        content = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode()
        resp = MagicMock()
        resp.status = status
        resp.status_code = status
        err = HttpError(resp=resp, content=content)
        return err

    def test_quota_exceeded_raises_typed_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        mock_service = MagicMock()
        client._service = mock_service

        quota_error = self._make_http_error(403, "quotaExceeded")
        mock_service.videos.return_value.insert.return_value.next_chunk.side_effect = quota_error

        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"fake")

        with patch("replaytagger.youtube_client.MediaFileUpload"):
            with pytest.raises(YouTubeQuotaExceededError) as exc_info:
                client.upload(fake_clip, "Apex Legends")

        assert "quota" in str(exc_info.value).lower()
        assert "midnight" in str(exc_info.value).lower()

    def test_daily_limit_exceeded_raises_typed_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        mock_service = MagicMock()
        client._service = mock_service

        quota_error = self._make_http_error(403, "dailyLimitExceeded")
        mock_service.videos.return_value.insert.return_value.next_chunk.side_effect = quota_error

        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"fake")

        with patch("replaytagger.youtube_client.MediaFileUpload"):
            with pytest.raises(YouTubeQuotaExceededError):
                client.upload(fake_clip, "Apex Legends")

    def test_rate_limit_429_raises_typed_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        mock_service = MagicMock()
        client._service = mock_service

        rate_error = self._make_http_error(429, "rateLimitExceeded")
        mock_service.videos.return_value.insert.return_value.next_chunk.side_effect = rate_error

        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"fake")

        with patch("replaytagger.youtube_client.MediaFileUpload"):
            with pytest.raises(YouTubeQuotaExceededError) as exc_info:
                client.upload(fake_clip, "Apex Legends")

        assert "429" in str(exc_info.value)
        assert "midnight" in str(exc_info.value).lower()

    def test_upload_limit_exceeded_raises_typed_error(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        mock_service = MagicMock()
        client._service = mock_service

        limit_error = self._make_http_error(400, "uploadLimitExceeded")
        mock_service.videos.return_value.insert.return_value.next_chunk.side_effect = limit_error

        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"fake")

        with patch("replaytagger.youtube_client.MediaFileUpload"):
            with pytest.raises(YouTubeQuotaExceededError) as exc_info:
                client.upload(fake_clip, "Apex Legends")

        assert "upload limit" in str(exc_info.value).lower()

    def test_other_403_reraises_http_error(self, tmp_path: Path) -> None:
        from googleapiclient.errors import HttpError

        client = _make_client(tmp_path)
        mock_service = MagicMock()
        client._service = mock_service

        other_error = self._make_http_error(403, "forbidden")
        mock_service.videos.return_value.insert.return_value.next_chunk.side_effect = other_error

        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"fake")

        with patch("replaytagger.youtube_client.MediaFileUpload"):
            with pytest.raises(HttpError):
                client.upload(fake_clip, "Apex Legends")


class TestUploadTags:
    def test_upload_does_not_include_nvidia_tag(self, tmp_path: Path) -> None:
        client = _make_client(tmp_path)
        mock_service = MagicMock()
        client._service = mock_service

        mock_insert = mock_service.videos.return_value.insert.return_value
        mock_insert.next_chunk.return_value = (None, {"id": "vid123"})

        fake_clip = tmp_path / "clip.mp4"
        fake_clip.write_bytes(b"fake")

        with patch("replaytagger.youtube_client.MediaFileUpload"):
            client.upload(fake_clip, "Apex Legends", privacy="private")

        _, kwargs = mock_service.videos.return_value.insert.call_args
        tags = kwargs["body"]["snippet"]["tags"]
        assert "NVIDIA" not in tags
        assert "Apex Legends" in tags
        assert "gaming" in tags
        assert "clips" in tags
