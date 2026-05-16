from __future__ import annotations

import json
import time
import uuid
import webbrowser
from pathlib import Path
from urllib import request
from urllib.error import URLError

PLEX_API = "https://plex.tv/api/v2"
PRODUCT = "ReplayTagger"
POLL_INTERVAL = 2
TIMEOUT_SECONDS = 120


def _client_id(data_dir: Path) -> str:
    """Return a stable client ID, creating one on first run."""
    path = data_dir / "plex_client_id"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text().strip()
    client_id = str(uuid.uuid4())
    path.write_text(client_id)
    return client_id


def _headers(client_id: str) -> dict[str, str]:
    return {
        "X-Plex-Product": PRODUCT,
        "X-Plex-Client-Identifier": client_id,
        "Accept": "application/json",
    }


def authenticate(data_dir: Path) -> str:
    """Run the Plex PIN OAuth flow and return a permanent auth token."""
    client_id = _client_id(data_dir)
    headers = _headers(client_id)

    # Request a PIN
    req = request.Request(
        f"{PLEX_API}/pins",
        method="POST",
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
        data=b"strong=true",
    )
    try:
        with request.urlopen(req) as resp:
            pin = json.loads(resp.read())
    except URLError as exc:
        raise RuntimeError(f"Could not reach plex.tv: {exc}") from exc

    pin_id: int = pin["id"]
    pin_code: str = pin["code"]

    auth_url = (
        f"https://app.plex.tv/auth#"
        f"?clientID={client_id}"
        f"&code={pin_code}"
        f"&context[device][product]={PRODUCT}"
    )

    print("Opening Plex authorization in your browser...")
    print(f"If it doesn't open automatically, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for you to authorize in the browser", end="", flush=True)
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        print(".", end="", flush=True)

        try:
            req = request.Request(f"{PLEX_API}/pins/{pin_id}", headers=headers)
            with request.urlopen(req) as resp:
                result = json.loads(resp.read())
        except URLError:
            continue

        if result.get("authToken"):
            print()
            return str(result["authToken"])

    raise TimeoutError("Plex authorization timed out after 2 minutes.")
