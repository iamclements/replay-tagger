from __future__ import annotations

import uuid
import warnings

import requests
import structlog
from plexapi.exceptions import NotFound, Unauthorized
from plexapi.server import PlexServer

log = structlog.get_logger(__name__)


class PlexClient:
    """Thin wrapper around plexapi for ReplayTagger's needs."""

    def __init__(self, url: str, token: str, library_name: str, verify_ssl: bool = True) -> None:
        self._url = url
        self._token = token
        self._library_name = library_name
        self._verify_ssl = verify_ssl
        self._server: PlexServer | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            session = requests.Session()
            session.verify = self._verify_ssl
            session.headers.update(
                {
                    "X-Plex-Product": "ReplayTagger",
                    "X-Plex-Device-Name": "ReplayTagger",
                    # Stable ID per server; prevents Plex registering a new device on each restart
                    "X-Plex-Client-Identifier": str(uuid.uuid5(uuid.NAMESPACE_URL, self._url)),
                }
            )
            if not self._verify_ssl:
                log.warning("plex_ssl_verification_disabled", url=self._url)
                warnings.filterwarnings("ignore", message="Unverified HTTPS request")
            self._server = PlexServer(self._url, self._token, session=session)  # type: ignore[no-untyped-call]
            log.info("plex_connected", url=self._url)
        except Unauthorized:
            log.error("plex_auth_failed", url=self._url, hint="Check PLEX_TOKEN")
            raise
        except Exception as exc:
            log.error("plex_connect_failed", url=self._url, error=str(exc))
            raise

    @property
    def _library(self):  # type: ignore[no-untyped-def]
        assert self._server is not None
        try:
            return self._server.library.section(self._library_name)
        except NotFound:
            raise ValueError(
                f"Plex library '{self._library_name}' not found. "
                "Check the library_name setting in config.yaml."
            )

    def scan(self) -> None:
        """Trigger an incremental library scan."""
        try:
            self._library.update()
            log.info("plex_scan_triggered", library=self._library_name)
        except Exception as exc:
            log.warning("plex_scan_failed", error=str(exc))

    def ensure_collection(self, game_name: str) -> None:
        """Create a smart collection for a game if one doesn't already exist."""
        lib = self._library
        try:
            existing = {c.title for c in lib.collections()}
            if game_name in existing:
                log.debug("collection_exists", game=game_name)
                return

            lib.createCollection(
                title=game_name,
                smart=True,
                filters={"genre": game_name},
            )
            log.info("collection_created", game=game_name)
        except Exception as exc:
            log.warning("collection_create_failed", game=game_name, error=str(exc))

    def list_collections(self) -> list[str]:
        return [c.title for c in self._library.collections()]
