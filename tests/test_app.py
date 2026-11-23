import asyncio
import io
import sys
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import create_app
from app.models import PreviewRequest
from app.runtime import Runtime

URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
SONG = {
    "name": "Test track",
    "artists": ["Test artist"],
    "duration": 65,
    "album_name": "Test album",
    "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    async def events(self, key, request):
        if request["operation"] == "preview":
            yield {"event": "preview", "songs": [SONG, {**SONG, "name": "Second track"}]}
            return
        for i, track in enumerate(request["tracks"]):
            if track["status"] == "completed":
                continue
            yield {"event": "start", "index": i}
            if track["song"]["name"] == "Second track" and not getattr(self, "succeed", False):
                yield {"event": "track_error", "index": i, "error": "Unavailable source"}
                continue
            path = Path(request["output"]) / f"{i}.mp3"
            path.write_bytes(b"ID3-test-audio")
            yield {"event": "progress", "index": i, "progress": 60, "message": "Downloading"}
            yield {"event": "complete", "index": i, "file": str(path), "size": path.stat().st_size}

    monkeypatch.setattr(Runtime, "events", events)
    app = create_app(tmp_path)
    with TestClient(app) as test_client:
        yield test_client


def wait_job(client, key):
    for _ in range(100):
        job = client.get(f"/api/jobs/{key}").json()
        if job["status"] not in {"queued", "downloading"}:
            return job
        time.sleep(0.01)
    raise AssertionError("Job did not finish")


def enqueue(client, indices=None):
    preview = client.post("/api/preview", json={"url": URL}).json()
    response = client.post("/api/jobs", json={"preview_id": preview["id"], "indices": indices or [0, 1]})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/track/" + "a" * 22,
        "http://open.spotify.com/track/" + "a" * 22,
        "https://open.spotify.com.evil/track/" + "a" * 22,
        "https://open.spotify.com/artist/" + "a" * 22,
        "file:///etc/passwd",
        "--help",
    ],
)
def test_reject_untrusted_urls(value):
    with pytest.raises(ValueError):
        PreviewRequest(url=value)


@pytest.mark.parametrize(
    "value",
    [
        "spotify:track:4cOdK2wGLETKBW3PvgPWqT",
        "https://open.spotify.com/intl-en/track/4cOdK2wGLETKBW3PvgPWqT?si=abc",
    ],
)
def test_normalize_urls(value):
    assert PreviewRequest(url=value).url == SONG["url"]


def test_preview_uses_server_metadata(client):
    response = client.post("/api/preview", json={"url": URL})
    assert response.status_code == 200
    assert len(response.json()["songs"]) == 2
    assert response.json()["kind"] == "playlist"


def test_selection_and_file_range_zip(client):
    job = wait_job(client, enqueue(client, [0, 0])["id"])
    assert job["status"] == "completed"
    assert len(job["tracks"]) == 1
    assert job["tracks"][0]["file"] is True
    path = f"/api/jobs/{job['id']}"
    response = client.get(path + "/tracks/0/file", headers={"Range": "bytes=0-2"})
    assert response.status_code == 206
    assert response.content == b"ID3"
    bundle = client.get(path + "/zip")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert archive.read(archive.namelist()[0]) == b"ID3-test-audio"
    assert not list(client.app.state.root.glob("*.zip"))


def test_partial_failure_retry_preserves_completed(client):
    job = wait_job(client, enqueue(client)["id"])
    assert job["status"] == "partial"
    assert job["tracks"][1]["error"] == "Unavailable source"
    file = client.app.state.root / "downloads" / job["id"] / "0.mp3"
    stamp = file.stat().st_mtime_ns
    client.app.state.runtime.succeed = True
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 200
    assert wait_job(client, job["id"])["status"] == "completed"
    assert file.stat().st_mtime_ns == stamp


def test_invalid_selection_and_missing_preview(client):
    preview = client.post("/api/preview", json={"url": URL}).json()
    for indices in ([], [-1], [2]):
        assert (
            client.post("/api/jobs", json={"preview_id": preview["id"], "indices": indices}).status_code
            == 422
        )
    assert client.post("/api/jobs", json={"preview_id": "unknown", "indices": [0]}).status_code == 404


def test_delete_removes_media_and_history(client):
    job = wait_job(client, enqueue(client, [0])["id"])
    base = f"/api/jobs/{job['id']}"
    assert client.post(base + "/retry").status_code == 409
    assert client.delete(base).status_code == 204
    assert client.get(base).status_code == 404
    assert not (client.app.state.root / "downloads" / job["id"]).exists()


def test_preferences_are_persisted(client):
    assert client.get("/api/preferences").json() == {"format": "mp3", "bitrate": "auto"}
    assert client.put("/api/preferences", json={"format": "opus", "bitrate": "128k"}).status_code == 200
    assert Database(client.app.state.root).preferences()["format"] == "opus"
    assert client.put("/api/preferences", json={"format": "exe"}).status_code == 422


def test_cross_origin_and_host_rejected(client):
    assert (
        client.post("/api/preview", json={"url": URL}, headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.get("/api/jobs", headers={"Host": "evil.example"}).status_code == 400


def test_api_and_missing_files_are_not_spa(client):
    assert client.get("/api/missing").status_code == 404
    assert client.get("/api/jobs/missing/zip").status_code == 404
    job = wait_job(client, enqueue(client, [0])["id"])
    assert client.get(f"/api/jobs/{job['id']}/tracks/-1/file").status_code == 404
    assert client.get(f"/api/jobs/{job['id']}/tracks/5/file").status_code == 404
    stored = client.app.state.db.get("jobs", job["id"])
    stored["tracks"][0]["file"] = "/etc/passwd"
    client.app.state.db.put("jobs", stored)
    assert client.get(f"/api/jobs/{job['id']}/tracks/0/file").status_code == 404


def test_restart_marks_unfinished_jobs_interrupted(tmp_path):
    db = Database(tmp_path)
    job = db.create_job(
        {"title": "Restart", "url": URL, "kind": "playlist", "songs": [SONG]}, [0], "mp3", "auto"
    )
    with TestClient(create_app(tmp_path)) as client:
        result = client.get(f"/api/jobs/{job['id']}").json()
        assert result["status"] == "interrupted"
        assert "Server restarted" in result["error"]


def test_cancel_running_job_and_prevent_active_delete(client, monkeypatch):
    async def slow_events(self, key, request):
        yield {"event": "start", "index": 0}
        await asyncio.sleep(60)

    monkeypatch.setattr(Runtime, "events", slow_events)
    preview = {"id": "slow", "title": "Slow", "url": URL, "kind": "track", "songs": [SONG]}
    client.app.state.db.put("previews", preview)
    job = client.post("/api/jobs", json={"preview_id": "slow", "indices": [0]}).json()
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 409
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 200
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "cancelled"


def test_preview_failure_is_useful(client, monkeypatch):
    async def broken(self, url):
        raise RuntimeError("Spotify service unavailable")

    monkeypatch.setattr(Runtime, "preview", broken)
    response = client.post("/api/preview", json={"url": URL})
    assert response.status_code == 502
    assert response.json()["detail"] == "Spotify service unavailable"


def test_timeout_closes_preview_iterator(client, monkeypatch):
    closed = []

    async def stalled(self, key, request):
        try:
            await asyncio.sleep(60)
            yield {}
        finally:
            closed.append(True)

    monkeypatch.setattr(Runtime, "events", stalled)
    monkeypatch.setenv("SPOTDL_PREVIEW_TIMEOUT", "0")
    response = client.post("/api/preview", json={"url": URL})
    assert response.status_code == 504
    assert closed == [True]


def test_real_process_cancellation(tmp_path):
    async def check():
        runtime = Runtime(tmp_path, Database(tmp_path))
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", "import time; time.sleep(60)", start_new_session=True
        )
        await runtime.stop_process(proc)
        assert proc.returncode is not None and proc.returncode < 0

    asyncio.run(check())


def test_second_server_cannot_share_database(tmp_path):
    with TestClient(create_app(tmp_path)):
        with pytest.raises(RuntimeError, match="already in use"), TestClient(create_app(tmp_path)):
            pass
