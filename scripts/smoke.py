"""Exercise the real spotDL child process using generated audio, never external music.

Creates a temporary workspace and HTTP source, downloads through the SDK, verifies
metadata and formats, serves range requests, builds a ZIP, then deletes everything.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    from spotdl.types.song import Song

    with tempfile.TemporaryDirectory(prefix="side-a-smoke-") as temp:
        directory = Path(temp)
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=2",
                str(directory / "tone.wav"),
            ],
            check=True,
        )
        source = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=temp))
        threading.Thread(target=source.serve_forever, daemon=True).start()
        try:
            song = Song(
                name="Generated test tone",
                artists=["Side A"],
                artist="Side A",
                genres=[],
                disc_number=1,
                disc_count=1,
                album_name="Integration check",
                album_artist="Side A",
                duration=2,
                year=2026,
                date="2026-01-01",
                track_number=1,
                tracks_count=1,
                song_id="test",
                album_id="local-test-album",
                explicit=False,
                publisher="",
                url="https://open.spotify.com/track/" + "a" * 22,
                isrc=None,
                cover_url=None,
                copyright_text=None,
                download_url=f"http://127.0.0.1:{source.server_port}/tone.wav",
            )
            with TestClient(create_app(directory / "data")) as client:
                db = client.app.state.db
                db.put(
                    "previews",
                    {
                        "id": "smoke",
                        "title": "Generated audio",
                        "url": song.url,
                        "kind": "track",
                        "songs": [asdict(song)],
                    },
                )
                for fmt in ("mp3", "m4a", "opus", "flac"):
                    job = client.post(
                        "/api/jobs", json={"preview_id": "smoke", "indices": [0], "format": fmt}
                    ).json()
                    for _ in range(300):
                        job = client.get(f"/api/jobs/{job['id']}").json()
                        if job["status"] not in {"queued", "downloading"}:
                            break
                        time.sleep(0.1)
                    assert job["status"] == "completed", job
                    stored = db.get("jobs", job["id"])
                    path = Path(stored["tracks"][0]["file"])
                    probe = json.loads(
                        subprocess.check_output(
                            [
                                "ffprobe",
                                "-v",
                                "quiet",
                                "-show_format",
                                "-show_streams",
                                "-of",
                                "json",
                                str(path),
                            ]
                        )
                    )
                    assert float(probe["format"]["duration"]) >= 1.9
                    # All offered formats must contain the Spotify-style title and artist tags.
                    tags = {
                        k.lower(): v for stream in probe["streams"] for k, v in stream.get("tags", {}).items()
                    }
                    tags.update({k.lower(): v for k, v in probe["format"].get("tags", {}).items()})
                    assert tags["title"] == song.name, tags
                    assert tags["artist"] == "Side A", tags
                    response = client.get(
                        f"/api/jobs/{job['id']}/tracks/0/file", headers={"Range": "bytes=0-9"}
                    )
                    assert response.status_code == 206 and len(response.content) == 10
                    archive = client.get(f"/api/jobs/{job['id']}/zip")
                    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
                        assert bundle.read(bundle.namelist()[0]) == path.read_bytes()
                    assert client.delete(f"/api/jobs/{job['id']}").status_code == 204
                    assert not path.exists()
                    print(
                        f"PASS {fmt}: real spotDL → {probe['streams'][0]['codec_name']}, metadata, playback ranges, ZIP, deletion",
                        flush=True,
                    )
                assert not client.get("/api/jobs").json()
        finally:
            source.shutdown()
            source.server_close()


if __name__ == "__main__":
    os.environ["PATH"] = str(ROOT / ".tools" / "node" / "bin") + os.pathsep + os.environ["PATH"]
    main()
