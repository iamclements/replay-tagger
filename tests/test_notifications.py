from unittest.mock import MagicMock, patch

from replaytagger.config import WebhookConfig
from replaytagger.notifications import (
    NotificationClient,
    NotifyEvent,
    _discord_payload,
    _generic_payload,
)


def _discord(events=None) -> WebhookConfig:
    return WebhookConfig(
        url="https://discord.com/api/webhooks/test/token",
        type="discord",
        events=events or ["scan_complete", "error"],
    )


def _generic(events=None) -> WebhookConfig:
    return WebhookConfig(
        url="https://example.com/webhook",
        type="generic",
        events=events or ["scan_complete", "error"],
    )


# ── payload builders ────────────────────────────────────────────────────────


def test_discord_payload_structure():
    payload = _discord_payload(NotifyEvent.SCAN_COMPLETE, {"tagged": 5, "total": 10})
    embed = payload["embeds"][0]
    assert embed["title"] == "ReplayTagger: Scan Complete"
    assert embed["color"] == 0x5865F2
    fields = {f["name"]: f["value"] for f in embed["fields"]}
    assert fields["tagged"] == "5"
    assert fields["total"] == "10"


def test_discord_error_color():
    payload = _discord_payload(NotifyEvent.ERROR, {"file": "clip.mp4", "error": "boom"})
    assert payload["embeds"][0]["color"] == 0xED4245


def test_generic_payload_structure():
    payload = _generic_payload(NotifyEvent.SCAN_COMPLETE, {"tagged": 3})
    assert payload["event"] == "scan_complete"
    assert payload["data"]["tagged"] == 3


# ── NotificationClient ──────────────────────────────────────────────────────


@patch("replaytagger.notifications.requests.post")
def test_sends_to_matching_webhook(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    client = NotificationClient([_discord()])
    client.notify(NotifyEvent.SCAN_COMPLETE, tagged=2, total=5)
    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert "embeds" in payload


@patch("replaytagger.notifications.requests.post")
def test_event_filter_skips_non_matching(mock_post):
    client = NotificationClient([_discord(events=["error"])])
    client.notify(NotifyEvent.SCAN_COMPLETE, tagged=0)
    mock_post.assert_not_called()


@patch("replaytagger.notifications.requests.post")
def test_multiple_webhooks_all_fire(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    client = NotificationClient([_discord(), _generic()])
    client.notify(NotifyEvent.SCAN_COMPLETE, tagged=1, total=1)
    assert mock_post.call_count == 2


@patch("replaytagger.notifications.requests.post")
def test_failed_request_logs_warning_does_not_raise(mock_post):
    mock_post.side_effect = Exception("connection refused")
    client = NotificationClient([_discord()])
    client.notify(NotifyEvent.ERROR, file="clip.mp4", error="ffmpeg failed")  # must not raise


@patch("replaytagger.notifications.requests.post")
def test_http_error_logs_warning_does_not_raise(mock_post):
    mock_post.return_value.raise_for_status.side_effect = Exception("429 Too Many Requests")
    client = NotificationClient([_discord()])
    client.notify(NotifyEvent.SCAN_COMPLETE, tagged=0)  # must not raise


@patch("replaytagger.notifications.requests.post")
def test_unknown_type_falls_back_to_generic(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    wh = WebhookConfig(url="https://example.com", type="slack", events=["scan_complete"])
    client = NotificationClient([wh])
    client.notify(NotifyEvent.SCAN_COMPLETE, tagged=0)
    payload = mock_post.call_args.kwargs["json"]
    assert payload["event"] == "scan_complete"


@patch("replaytagger.notifications.requests.post")
def test_ntfy_posts_plaintext_with_title(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    wh = WebhookConfig(url="https://ntfy.sh/my-topic", type="ntfy", events=["scan_complete"])
    client = NotificationClient([wh])
    client.notify(NotifyEvent.SCAN_COMPLETE, tagged=2, total=5)
    mock_post.assert_called_once()
    # ntfy uses a plaintext body, not a JSON payload.
    assert "json" not in mock_post.call_args.kwargs
    body = mock_post.call_args.kwargs["data"].decode("utf-8")
    assert "tagged: 2" in body
    assert "total: 5" in body
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Title"] == "ReplayTagger: Scan Complete"


@patch("replaytagger.notifications.requests.post")
def test_clip_tagged_event(mock_post):
    mock_post.return_value.raise_for_status = MagicMock()
    client = NotificationClient([_discord(events=["clip_tagged"])])
    client.notify(NotifyEvent.CLIP_TAGGED, game="Apex Legends", file="clip1.mp4")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["embeds"][0]["color"] == 0x57F287
