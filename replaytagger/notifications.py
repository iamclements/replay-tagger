from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

import requests
import structlog

if TYPE_CHECKING:
    from replaytagger.config import WebhookConfig

log = structlog.get_logger(__name__)


class NotifyEvent(StrEnum):
    CLIP_TAGGED = "clip_tagged"
    CLIP_UPLOADED = "clip_uploaded"
    SCAN_COMPLETE = "scan_complete"
    ERROR = "error"


_DISCORD_COLORS: dict[NotifyEvent, int] = {
    NotifyEvent.CLIP_TAGGED: 0x57F287,
    NotifyEvent.CLIP_UPLOADED: 0xFEE75C,
    NotifyEvent.SCAN_COMPLETE: 0x5865F2,
    NotifyEvent.ERROR: 0xED4245,
}

_DISCORD_TITLES: dict[NotifyEvent, str] = {
    NotifyEvent.CLIP_TAGGED: "Clip Tagged",
    NotifyEvent.CLIP_UPLOADED: "Clip Uploaded to YouTube",
    NotifyEvent.SCAN_COMPLETE: "Scan Complete",
    NotifyEvent.ERROR: "Error",
}


def _discord_payload(event: NotifyEvent, data: dict[str, Any]) -> dict[str, Any]:
    fields = [{"name": k, "value": str(v), "inline": True} for k, v in data.items()]
    return {
        "embeds": [
            {
                "title": f"ReplayTagger: {_DISCORD_TITLES[event]}",
                "color": _DISCORD_COLORS[event],
                "fields": fields,
            }
        ]
    }


def _generic_payload(event: NotifyEvent, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": event.value, "data": data}


_BUILDERS = {
    "discord": _discord_payload,
    "generic": _generic_payload,
}


class NotificationClient:
    def __init__(self, webhooks: list[WebhookConfig]) -> None:
        self._webhooks = webhooks

    def notify(self, event: NotifyEvent, **data: object) -> None:
        for wh in self._webhooks:
            if event.value not in wh.events:
                continue
            builder = _BUILDERS.get(wh.type, _generic_payload)
            try:
                payload = builder(event, data)
                resp = requests.post(wh.url, json=payload, timeout=10)
                resp.raise_for_status()
                log.debug("notification_sent", type=wh.type, notify_event=event.value)
            except Exception as exc:
                log.warning(
                    "notification_failed",
                    type=wh.type,
                    notify_event=event.value,
                    error=str(exc),
                )
