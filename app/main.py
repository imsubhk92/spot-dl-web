import fcntl
import importlib.metadata
import os
import shutil
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import ROOT, data_dir
from app.db import Database
from app.models import DownloadRequest, Preferences, PreviewRequest
from app.runtime import ACTIVE, Runtime


def create_app(root: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        directory = (root or data_dir()).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        lock = (directory / "server.lock").open("w")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError(
                "This data directory is already in use. Run a single Uvicorn worker."
            ) from None
        try:
            app.state.root = directory
            app.state.db = Database(directory)
            app.state.runtime = Runtime(directory, app.state.db)
            await app.state.runtime.start()
            yield
        finally:
            if hasattr(app.state, "runtime"):
                await app.state.runtime.stop()
            lock.close()

    app = FastAPI(title="Side A · spotDL Web", version="0.1.0", lifespan=lifespan)
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8002",
        "http://127.0.0.1:8002",
    ]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["Content-Type"]
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "DELETE", "PATCH"} and origin and origin not in origins:
            return JSONResponse(
                {"detail": "This local server does not accept requests from that origin."}, status_code=403
            )
        return await call_next(request)

    def job_or_404(key: str):
        job = app.state.db.get("jobs", key)
        if not job:
            raise HTTPException(404, "Download not found.")
        return job

    def file_or_404(job: dict, index: int):
        if index < 0 or index >= len(job["tracks"]):
            raise HTTPException(404, "Track not found.")
        track = job["tracks"][index]
        path = Path(track.get("file") or "").resolve()
        base = (app.state.root / "downloads" / job["id"]).resolve()
        if track["status"] != "completed" or not path.is_relative_to(base) or not path.is_file():
            raise HTTPException(404, "Audio file is unavailable.")
        return path

    def public_job(job: dict):
        return {**job, "tracks": [{**t, "file": bool(t.get("file"))} for t in job["tracks"]]}

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "spotdl": importlib.metadata.version("spotdl"),
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "javascript_runtime": bool(shutil.which("node") or shutil.which("deno")),
            "spotify_credentials": bool(
                os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET")
            ),
            "cookies": bool(
                os.getenv("SPOTDL_COOKIE_FILE") and Path(os.environ["SPOTDL_COOKIE_FILE"]).is_file()
            ),
        }

    @app.post("/api/preview")
    async def preview(body: PreviewRequest):
        try:
            return await app.state.runtime.preview(body.url)
        except TimeoutError:
            raise HTTPException(
                504, "Spotify took too long to respond. Try again or check your server credentials."
            ) from None
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.get("/api/jobs")
    def jobs():
        return [public_job(j) for j in app.state.db.all_jobs()]

    @app.get("/api/jobs/{key}")
    def get_job(key: str):
        return public_job(job_or_404(key))

    @app.post("/api/jobs", status_code=201)
    async def create_job(body: DownloadRequest):
        preview = app.state.db.get("previews", body.preview_id)
        if not preview:
            raise HTTPException(404, "Preview expired or not found. Preview the link again.")
        if any(i < 0 or i >= len(preview["songs"]) for i in body.indices):
            raise HTTPException(422, "Selected track is outside this playlist.")
        if sum(j["status"] in ACTIVE for j in app.state.db.all_jobs()) >= 50:
            raise HTTPException(409, "The queue is full. Wait for downloads to finish.")
        job = app.state.db.create_job(preview, body.indices, body.format, body.bitrate)
        app.state.runtime.queue.put_nowait(job["id"])
        return public_job(job)

    @app.post("/api/jobs/{key}/cancel")
    async def cancel(key: str):
        job = job_or_404(key)
        if job["status"] not in ACTIVE:
            raise HTTPException(409, "This download is no longer active.")
        await app.state.runtime.cancel(job)
        return public_job(app.state.db.get("jobs", key))

    @app.post("/api/jobs/{key}/retry")
    async def retry(key: str):
        job = job_or_404(key)
        if job["status"] in ACTIVE or job["status"] == "completed":
            raise HTTPException(409, "Only unfinished downloads can be retried.")
        for track in job["tracks"]:
            if track["status"] != "completed":
                track.update(status="queued", progress=0, message="Waiting", error=None)
        job.update(status="queued", error=None)
        app.state.db.put("jobs", job)
        app.state.runtime.queue.put_nowait(key)
        return public_job(job)

    @app.delete("/api/jobs/{key}", status_code=204)
    async def delete(key: str):
        job = job_or_404(key)
        if job["status"] in ACTIVE:
            raise HTTPException(409, "Cancel this download before deleting it.")
        directory = app.state.root / "downloads" / key
        if directory.exists():
            shutil.rmtree(directory)
        app.state.db.delete_job(key)

    @app.get("/api/jobs/{key}/tracks/{index}/file")
    def audio_file(key: str, index: int, inline: bool = False):
        path = file_or_404(job_or_404(key), index)
        return FileResponse(
            path, filename=path.name, content_disposition_type="inline" if inline else "attachment"
        )

    @app.get("/api/jobs/{key}/zip")
    def archive(key: str):
        job = job_or_404(key)
        paths = [
            (i, file_or_404(job, i))
            for i, track in enumerate(job["tracks"])
            if track["status"] == "completed"
        ]
        if not paths:
            raise HTTPException(409, "No completed tracks to archive yet.")
        handle, name = tempfile.mkstemp(suffix=".zip", dir=app.state.root)
        os.close(handle)
        try:
            with zipfile.ZipFile(name, "w", zipfile.ZIP_STORED) as bundle:
                for i, path in paths:
                    bundle.write(path, f"{i + 1:03d} - {path.name}")
        except Exception:
            Path(name).unlink(missing_ok=True)
            raise
        return FileResponse(
            name,
            filename=f"{job['title'][:100].replace('/', '-')}.zip",
            background=BackgroundTask(Path(name).unlink, missing_ok=True),
        )

    @app.get("/api/preferences")
    def preferences():
        return app.state.db.preferences()

    @app.put("/api/preferences")
    def save_preferences(body: Preferences):
        return app.state.db.preferences(body.model_dump())

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API endpoint not found.")
        directory = ROOT / "frontend" / "dist"
        candidate = (directory / path).resolve()
        if candidate.is_relative_to(directory.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        if (directory / "index.html").is_file():
            return FileResponse(directory / "index.html")
        return JSONResponse(
            {"message": "Build the frontend with make build, or open the Vite dev server on port 5173."}
        )

    return app


app = create_app()
