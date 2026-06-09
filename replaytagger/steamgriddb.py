from __future__ import annotations

import urllib.parse

import requests
import structlog

log = structlog.get_logger(__name__)

_BASE = "https://www.steamgriddb.com/api/v2"


def fetch_portrait_url(game_name: str, api_key: str) -> str | None:
    """Return the URL of the best portrait grid art for game_name, or None.

    Uses SteamGridDB (steamgriddb.com) - covers Steam, Ubisoft Connect,
    Battle.net, and community-submitted art for modded/private clients.
    Never raises; all failures are logged at debug level.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        encoded = urllib.parse.quote(game_name, safe="")
        r = requests.get(
            f"{_BASE}/search/autocomplete/{encoded}",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        items = r.json().get("data", [])
        if not items:
            log.debug("sgdb_no_results", game=game_name)
            return None

        game_id = items[0]["id"]

        r = requests.get(
            f"{_BASE}/grids/game/{game_id}",
            headers=headers,
            params={"dimensions": "600x900,342x482", "nsfw": "false", "humor": "false"},
            timeout=10,
        )
        r.raise_for_status()
        grids = r.json().get("data", [])
        if not grids:
            log.debug("sgdb_no_grids", game=game_name, game_id=game_id)
            return None

        url: str = grids[0]["url"]
        log.debug("sgdb_art_found", game=game_name, url=url)
        return url

    except Exception as exc:
        log.debug("sgdb_lookup_failed", game=game_name, error=str(exc))
        return None
