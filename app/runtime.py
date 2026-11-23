import asyncio
import json
import os
import shutil
import signal
import sys
from contextlib import aclosing
from pathlib import Path
from uuid import uuid4

from app.config import ROOT, worker_env
from app.db import Database, now

ACTIVE = {"queued", "downloading"}


class Runtime:
    def __init__(self, root: Path, db: Database):
        self.root, self.db = root, db
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.processes: dict[str, asyncio.subprocess.Process] = {}
        self.preview_slots = asyncio.Semaphore(2)

    async def start(self):
        # Incomplete media is never advertised as complete. Require explicit retry after a restart.
        for job in self.db.all_jobs():
            if job["status"] in ACTIVE:
                job.update(
                    status="interrupted", error="Server restarted. Retry to continue unfinished tracks."
                )
                for track in job["tracks"]:
                    if track["status"] == "downloading":
                        track.update(status="queued", progress=0)
                self.db.put("jobs", job)
        self.task = asyncio.create_task(self.consume())

    async def stop_process(self, proc):
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), 4)
            except TimeoutError:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()

    async def stop(self):
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        await asyncio.gather(*(self.stop_process(p) for p in list(self.processes.values())))

    async def events(self, key: str, request: dict):
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.worker",
            cwd=ROOT,
            env=worker_env(self.root / "workers" / key, self.root / "cache" / "spotify-queries"),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
            limit=16 * 1024 * 1024,
        )
        self.processes[key] = proc
        try:
            proc.stdin.write(json.dumps(request).encode())
            await proc.stdin.drain()
            proc.stdin.close()
            async for line in proc.stdout:
                yield json.loads(line)
            code = await proc.wait()
            if code:
                raise RuntimeError(
                    "spotDL stopped before finishing. Check your connection, credentials and source availability."
                )
        finally:
            await self.stop_process(proc)
            self.processes.pop(key, None)
            shutil.rmtree(self.root / "workers" / key, ignore_errors=True)

    async def preview(self, url: str):
        async with self.preview_slots:
            async with asyncio.timeout(int(os.getenv("SPOTDL_PREVIEW_TIMEOUT", "180"))):
                async with aclosing(
                    self.events("preview-" + uuid4().hex, {"operation": "preview", "url": url})
                ) as events:
                    async for event in events:
                        if event["event"] == "error":
                            raise RuntimeError(event["error"])
                        if event["event"] == "preview":
                            songs = event["songs"]
                            first = songs[0]
                            kind = url.split("/")[-2]
                            preview = {
                                "id": uuid4().hex,
                                "url": url,
                                "kind": kind,
                                "songs": songs,
                                "title": (first.get("list_name") or first.get("album_name"))
                                if kind != "track"
                                else first["name"],
                                "cover_url": first.get("cover_url"),
                                "created_at": now(),
                            }
                            self.db.put("previews", preview)
                            return preview
        raise RuntimeError("spotDL did not return any tracks.")

    async def cancel(self, job: dict):
        job.update(status="cancelled", updated_at=now(), error=None)
        for track in job["tracks"]:
            if track["status"] in ACTIVE:
                track.update(status="cancelled", message="Cancelled")
        self.db.put("jobs", job)
        if proc := self.processes.get(job["id"]):
            await self.stop_process(proc)

    async def consume(self):
        while True:
            key = await self.queue.get()
            try:
                job = self.db.get("jobs", key)
                if not job or job["status"] != "queued":
                    continue
                job.update(status="downloading", error=None, updated_at=now())
                self.db.put("jobs", job)
                output = self.root / "downloads" / key
                output.mkdir(parents=True, exist_ok=True)
                request = {
                    "operation": "download",
                    "output": str(output),
                    "format": job["format"],
                    "bitrate": job["bitrate"],
                    "tracks": job["tracks"],
                }
                try:
                    async with asyncio.timeout(int(os.getenv("SPOTDL_DOWNLOAD_TIMEOUT", "7200"))):
                        async with aclosing(self.events(key, request)) as events:
                            async for event in events:
                                job = self.db.get("jobs", key)
                                if job["status"] != "downloading":
                                    break
                                if event["event"] == "error":
                                    raise RuntimeError(event["error"])
                                track = job["tracks"][event["index"]]
                                match event["event"]:
                                    case "start":
                                        track.update(
                                            status="downloading",
                                            progress=0,
                                            message="Finding audio match",
                                            error=None,
                                        )
                                    case "progress":
                                        track.update(progress=event["progress"], message=event["message"])
                                    case "complete":
                                        file = Path(event["file"]).resolve()
                                        if not file.is_relative_to(output.resolve()) or not file.is_file():
                                            raise RuntimeError("Worker returned an invalid audio file.")
                                        track.update(
                                            status="completed",
                                            progress=100,
                                            message="Ready",
                                            file=str(file),
                                            size=event["size"],
                                        )
                                    case "track_error":
                                        track.update(
                                            status="failed",
                                            progress=0,
                                            message="Download failed",
                                            error=event["error"],
                                        )
                                job["updated_at"] = now()
                                self.db.put("jobs", job)
                    job = self.db.get("jobs", key)
                    if job["status"] == "downloading":
                        completed = sum(t["status"] == "completed" for t in job["tracks"])
                        job["status"] = (
                            "completed"
                            if completed == len(job["tracks"])
                            else "partial"
                            if completed
                            else "failed"
                        )
                        self.db.put("jobs", job)
                except Exception as exc:
                    job = self.db.get("jobs", key)
                    if job and job["status"] == "downloading":
                        job.update(
                            status="failed", error=str(exc) or "Download timed out. Retry to continue."
                        )
                        for track in job["tracks"]:
                            if track["status"] in ACTIVE:
                                track.update(
                                    status="failed", progress=0, message="Interrupted", error=job["error"]
                                )
                        self.db.put("jobs", job)
            finally:
                self.queue.task_done()
