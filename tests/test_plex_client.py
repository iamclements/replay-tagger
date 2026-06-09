from __future__ import annotations

from unittest.mock import MagicMock, patch

from replaytagger.plex_client import PlexClient


def _make_client() -> PlexClient:
    with patch("replaytagger.plex_client.PlexServer"):
        client = PlexClient(
            url="https://plex.local:32400",
            token="faketoken",
            library_name="Gaming Clips",
            verify_ssl=False,
        )
    return client


def _mock_collection(title: str) -> MagicMock:
    c = MagicMock()
    c.title = title
    return c


class TestEnsureCollection:
    def _patched(self, client: PlexClient, lib: MagicMock):  # type: ignore[no-untyped-def]
        return patch.object(
            type(client), "_library", new_callable=lambda: property(lambda self: lib)
        )

    def test_skips_creation_when_exact_match_exists(self) -> None:
        client = _make_client()
        lib = MagicMock()
        lib.collections.return_value = [_mock_collection("Apex Legends")]
        with self._patched(client, lib):
            result = client.ensure_collection("Apex Legends")
        assert result is None
        lib.createCollection.assert_not_called()

    def test_skips_creation_on_case_mismatch(self) -> None:
        # Plex may store the collection as "XDefiant" while the folder name is "Xdefiant".
        client = _make_client()
        lib = MagicMock()
        lib.collections.return_value = [_mock_collection("XDefiant")]
        with self._patched(client, lib):
            result = client.ensure_collection("Xdefiant")
        assert result is None
        lib.createCollection.assert_not_called()

    def test_creates_collection_when_absent(self) -> None:
        client = _make_client()
        lib = MagicMock()
        lib.collections.return_value = [_mock_collection("Apex Legends")]
        with self._patched(client, lib):
            result = client.ensure_collection("Battlefield 6")
        assert result is lib.createCollection.return_value
        lib.createCollection.assert_called_once_with(
            title="Battlefield 6",
            smart=True,
            filters={"genre": "Battlefield 6"},
        )


class TestSetCollectionPoster:
    def test_calls_upload_poster(self) -> None:
        client = _make_client()
        collection = _mock_collection("Apex Legends")
        client.set_collection_poster(collection, "https://cdn.example.com/art.jpg")
        collection.uploadPoster.assert_called_once_with(url="https://cdn.example.com/art.jpg")

    def test_logs_warning_on_failure(self) -> None:
        client = _make_client()
        collection = _mock_collection("Apex Legends")
        collection.uploadPoster.side_effect = Exception("timeout")
        client.set_collection_poster(collection, "https://cdn.example.com/art.jpg")
