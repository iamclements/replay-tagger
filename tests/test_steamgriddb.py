from __future__ import annotations

from unittest.mock import MagicMock, patch

from replaytagger.steamgriddb import fetch_portrait_url

_API_KEY = "testkey"
_GAME_ID = 42


def _search_response(items: list[dict]) -> MagicMock:  # type: ignore[type-arg]
    r = MagicMock()
    r.json.return_value = {"success": True, "data": items}
    return r


def _grids_response(grids: list[dict]) -> MagicMock:  # type: ignore[type-arg]
    r = MagicMock()
    r.json.return_value = {"success": True, "data": grids}
    return r


class TestFetchPortraitUrl:
    def test_returns_url_on_success(self) -> None:
        expected_url = "https://cdn2.steamgriddb.com/grid/abc123.jpg"
        search = _search_response([{"id": _GAME_ID, "name": "Apex Legends"}])
        grids = _grids_response([{"url": expected_url, "width": 600, "height": 900}])

        with patch("replaytagger.steamgriddb.requests.get", side_effect=[search, grids]):
            result = fetch_portrait_url("Apex Legends", _API_KEY)

        assert result == expected_url

    def test_returns_none_when_no_search_results(self) -> None:
        search = _search_response([])

        with patch("replaytagger.steamgriddb.requests.get", return_value=search):
            result = fetch_portrait_url("Unknown Game XYZ", _API_KEY)

        assert result is None

    def test_returns_none_when_no_grids(self) -> None:
        search = _search_response([{"id": _GAME_ID, "name": "Some Game"}])
        grids = _grids_response([])

        with patch("replaytagger.steamgriddb.requests.get", side_effect=[search, grids]):
            result = fetch_portrait_url("Some Game", _API_KEY)

        assert result is None

    def test_returns_none_on_http_error(self) -> None:
        import requests as req

        with patch(
            "replaytagger.steamgriddb.requests.get",
            side_effect=req.exceptions.ConnectionError("unreachable"),
        ):
            result = fetch_portrait_url("Apex Legends", _API_KEY)

        assert result is None

    def test_returns_none_on_bad_status(self) -> None:
        r = MagicMock()
        r.raise_for_status.side_effect = Exception("401 Unauthorized")

        with patch("replaytagger.steamgriddb.requests.get", return_value=r):
            result = fetch_portrait_url("Apex Legends", _API_KEY)

        assert result is None

    def test_encodes_game_name_in_url(self) -> None:
        search = _search_response([])

        with patch("replaytagger.steamgriddb.requests.get", return_value=search) as mock_get:
            fetch_portrait_url("Call of Duty: Warzone", _API_KEY)

        call_url = mock_get.call_args[0][0]
        assert " " not in call_url
        assert "Call%20of%20Duty%3A%20Warzone" in call_url
