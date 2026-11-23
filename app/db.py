import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, root: Path):
        self.path = root / "library.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS previews (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def all_jobs(self) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM jobs ORDER BY rowid DESC")]

    def get(self, table: str, key: str) -> dict | None:
        assert table in {"jobs", "previews"}
        with self.connect() as db:
            row = db.execute(f"SELECT payload FROM {table} WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, table: str, payload: dict):
        assert table in {"jobs", "previews"}
        with self.connect() as db:
            db.execute(
                f"INSERT INTO {table} VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (payload["id"], json.dumps(payload)),
            )

    def delete_job(self, key: str):
        with self.connect() as db:
            db.execute("DELETE FROM jobs WHERE id=?", (key,))

    def preferences(self, payload: dict | None = None) -> dict:
        with self.connect() as db:
            if payload is not None:
                db.execute(
                    "INSERT INTO preferences VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (json.dumps(payload),),
                )
            row = db.execute("SELECT payload FROM preferences WHERE id=1").fetchone()
        return json.loads(row[0]) if row else {"format": "mp3", "bitrate": "auto"}

    def create_job(self, preview: dict, indices: list[int], fmt: str, bitrate: str) -> dict:
        job = {
            "id": uuid4().hex,
            "title": preview["title"],
            "url": preview["url"],
            "kind": preview["kind"],
            "cover_url": preview.get("cover_url"),
            "status": "queued",
            "created_at": now(),
            "updated_at": now(),
            "format": fmt,
            "bitrate": bitrate,
            "error": None,
            "tracks": [
                {
                    "song": preview["songs"][i],
                    "status": "queued",
                    "progress": 0,
                    "message": "Waiting",
                    "file": None,
                    "size": 0,
                    "error": None,
                }
                for i in sorted(set(indices))
            ],
        }
        self.put("jobs", job)
        return job
