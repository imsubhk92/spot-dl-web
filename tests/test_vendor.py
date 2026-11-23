import gzip
import importlib
import importlib.metadata
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from spotapi import _query_cache
from spotapi.client import BaseClient
from spotapi.http.request import TLSClient
from spotdl.utils import search


@pytest.fixture(autouse=True)
def isolate_catalog(tmp_path, monkeypatch):
    _query_cache._memory.clear()
    monkeypatch.setenv("SPOTAPI_CACHE_DIR", str(tmp_path / "catalog"))
    yield
    _query_cache._memory.clear()


@pytest.mark.parametrize(
    "package,module",
    [
        ("spotdl", "spotdl"),
        ("spotipyfree", "SpotipyFree"),
        ("spotapi", "spotapi"),
        ("yt-dlp", "yt_dlp"),
        ("ytmusicapi", "ytmusicapi"),
    ],
)
def test_core_packages_are_local(package, module):
    root = Path(__file__).resolve().parent.parent / "vendor"
    assert Path(importlib.import_module(module).__file__).is_relative_to(root)
    if package != "yt-dlp":
        assert "+sidea.1" in importlib.metadata.version(package)


def test_catalog_reuses_build_across_clients_and_process_restarts():
    loader = Mock(return_value='"getAlbum","query","' + "a" * 64 + '"')
    first = _query_cache.catalog("build-1", loader)
    _query_cache._memory.clear()  # Simulate another worker with the shared public disk cache.
    assert _query_cache.catalog("build-1", loader) == first
    assert loader.call_count == 1
    _query_cache.catalog("build-2", loader)
    assert loader.call_count == 2


def test_catalog_concurrent_loads_only_build_once():
    def load():
        time.sleep(0.02)
        return "public query catalog"

    loader = Mock(side_effect=load)
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: _query_cache.catalog("build", loader), range(4)))
    assert values == ["public query catalog"] * 4
    assert loader.call_count == 1


def test_corrupt_catalog_is_rebuilt(tmp_path):
    _query_cache.catalog("build", lambda: "original")
    _query_cache._memory.clear()
    path = next((tmp_path / "catalog").glob("*.txt.gz"))
    path.write_bytes(b"corrupt gzip")
    assert _query_cache.catalog("build", lambda: "repaired") == "repaired"
    assert gzip.decompress(path.read_bytes()) == b"repaired"


def test_catalog_failure_does_not_poison_cache():
    with pytest.raises(RuntimeError, match="temporary failure"):
        _query_cache.catalog("build", Mock(side_effect=RuntimeError("temporary failure")))
    assert _query_cache.catalog("build", lambda: "success") == "success"


def test_javascript_catalog_retains_chunk_order_and_is_shared(monkeypatch):
    import spotapi.client as source

    monkeypatch.setattr(source, "extract_mappings", lambda _: ({1: "first", 2: "second"}, {1: "a", 2: "b"}))
    monkeypatch.setattr(source, "combine_chunks", lambda *_: ["first.a.js", "second.b.js"])

    def get(url):
        if url.endswith("first.a.js"):
            time.sleep(0.02)
        return SimpleNamespace(fail=False, response="base" if url == "build" else url.split("/")[-1])

    client = object.__new__(BaseClient)
    client.js_pack = "build"
    client.client = SimpleNamespace(get=Mock(side_effect=get))
    client.get_sha256_hash()
    assert client.raw_hashes == "basefirst.a.jssecond.b.js"
    other = object.__new__(BaseClient)
    other.js_pack = "build"
    other.client = SimpleNamespace(get=Mock(side_effect=AssertionError("Should reuse catalog")))
    other.get_sha256_hash()
    assert other.raw_hashes == client.raw_hashes
    other.client.get.assert_not_called()


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_read_only_metadata_retries_temporary_server_errors(monkeypatch, code):
    first = SimpleNamespace(status_code=code, headers={}, close=Mock())
    success = SimpleNamespace(status_code=200)
    request = Mock(side_effect=[first, success])
    monkeypatch.setattr(TLSClient, "request", request)
    monkeypatch.setattr("spotapi.http.request.time.sleep", lambda _: None)
    client = TLSClient("chrome120", "", auto_retries=3)
    response = client.build_request(
        "POST", "https://api-partner.spotify.com/pathfinder/v1/query", params={"operationName": "getTrack"}
    )
    assert response.status_code == 200
    assert request.call_count == 2
    assert request.call_args.kwargs["timeout"] == (8, 20)


def test_write_requests_and_long_rate_limits_are_not_repeated(monkeypatch):
    response = SimpleNamespace(status_code=500, headers={}, close=Mock())
    request = Mock(return_value=response)
    monkeypatch.setattr(TLSClient, "request", request)
    client = TLSClient("chrome120", "", auto_retries=3)
    assert client.build_request("POST", "https://example.com/write").status_code == 500
    assert request.call_count == 1
    request.reset_mock()
    response.status_code = 429
    response.headers = {"Retry-After": "86400"}
    assert client.build_request("GET", "https://example.com/read").status_code == 429
    assert request.call_count == 1


def test_metadata_cache_normalizes_urls_and_returns_isolated_copies():
    from SpotipyFree.Spotify import Spotify, _cached_metadata

    calls = []

    class Catalog(Spotify):
        @_cached_metadata
        def sample(self, identifier):
            calls.append(identifier)
            return {"artists": ["Original"]}

    client = Catalog()
    url = "https://open.spotify.com/album/7xLyQXqKOix3czQCjrc1tF"
    first = client.sample(url)
    first["artists"].append("Mutated")
    assert client.sample("7xLyQXqKOix3czQCjrc1tF") == {"artists": ["Original"]}
    assert len(calls) == 1


def test_failed_track_is_reported_instead_of_silently_omitted(monkeypatch):
    songs = [SimpleNamespace(display_name="First"), SimpleNamespace(display_name="Missing")]
    monkeypatch.setattr(search, "get_simple_songs", lambda *_args, **_kwargs: songs)

    def resolve(song):
        if song.display_name == "Missing":
            raise RuntimeError("Spotify unavailable")
        return song

    monkeypatch.setattr(search, "reinit_song", resolve)
    with pytest.raises(search.QueryError, match="1 of 2 tracks.*Missing"):
        search.parse_query(["album"], threads=2)


def test_parallel_metadata_results_preserve_playlist_order(monkeypatch):
    songs = [SimpleNamespace(display_name="Slow"), SimpleNamespace(display_name="Fast")]
    monkeypatch.setattr(search, "get_simple_songs", lambda *_args, **_kwargs: songs)

    def resolve(song):
        if song.display_name == "Slow":
            time.sleep(0.02)
        return song

    monkeypatch.setattr(search, "reinit_song", resolve)
    assert search.parse_query(["album"], threads=2) == songs
