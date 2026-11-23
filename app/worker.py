"""Isolated spotDL SDK bridge. stdout is a JSON-lines event protocol only."""

import contextlib
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path


def emit(event: dict):
    sys.__stdout__.write(json.dumps(event) + "\n")
    sys.__stdout__.flush()


def safe_error(exc: Exception) -> str:
    message = str(exc)
    for key in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTDL_COOKIE_FILE"):
        secret = os.getenv(key)
        if secret:
            message = message.replace(secret, "[redacted]")
    return message[-1200:] or type(exc).__name__


def run(request: dict):
    from spotdl import Spotdl
    from spotdl.download.progress_handler import ProgressHandler
    from spotdl.types.song import Song
    from spotdl.utils.config import SPOTIFY_OPTIONS

    official = bool(os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET"))
    settings = {
        "threads": 1,
        "simple_tui": True,
        "lyrics_providers": [],
        "audio_providers": ["youtube-music", "youtube"],
        "format": request.get("format", "mp3"),
        "bitrate": None if request.get("bitrate", "auto") == "auto" else request["bitrate"],
        "overwrite": "force",
        "print_errors": True,
        "yt_dlp_args": "--js-runtimes node" if shutil.which("node") else None,
    }
    if os.getenv("SPOTDL_COOKIE_FILE"):
        # yt-dlp can update cookies. Give it a private copy, preserving the supplied file.
        cookie_copy = Path.home() / "youtube-cookies.txt"
        shutil.copyfile(os.environ["SPOTDL_COOKIE_FILE"], cookie_copy)
        cookie_copy.chmod(0o600)
        settings["cookie_file"] = str(cookie_copy)
    client = Spotdl(
        client_id=os.getenv("SPOTIFY_CLIENT_ID") or SPOTIFY_OPTIONS["client_id"],
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET") or SPOTIFY_OPTIONS["client_secret"],
        use_official_api=official,
        headless=True,
        no_cache=True,
        downloader_settings=settings,
    )
    if request["operation"] == "preview":
        try:
            songs = client.search([request["url"]])
        except (KeyError, TypeError) as exc:
            raise RuntimeError(
                "Spotify returned incomplete metadata. Check that this link is public and available, "
                "or configure your own Spotify API credentials on the server."
            ) from exc
        if not songs:
            raise ValueError("No tracks found. Check that the Spotify link is public and available.")
        if len(songs) > 1000:
            raise ValueError("This collection exceeds the 1,000-track limit. Use a smaller playlist.")
        emit({"event": "preview", "songs": [asdict(song) for song in songs]})
        return

    last = [0.0]
    current = [0]

    def progress(*_args):
        if time.monotonic() - last[0] < 0.4:
            return
        last[0] = time.monotonic()
        for entry in handler.progress_tracker.songs.values():
            emit(
                {
                    "event": "progress",
                    "index": current[0],
                    "progress": min(99, entry.progress),
                    "message": entry.message,
                }
            )

    handler = ProgressHandler(simple_tui=True, update_callback=progress, web_ui=True)
    client.downloader.progress_handler = handler
    for index, item in enumerate(request["tracks"]):
        if item["status"] == "completed" and item.get("file") and Path(item["file"]).is_file():
            continue
        current[0] = index
        handler.progress_tracker.songs.clear()
        emit({"event": "start", "index": index})
        try:
            song = Song(**item["song"])
            # spotDL's tag writer expects text even when Spotify omits this optional field.
            song.isrc = song.isrc or ""
            directory = Path(request["output"]) / str(index + 1).zfill(3)
            directory.mkdir(parents=True, exist_ok=True)
            client.downloader.settings["output"] = str(directory / "{artists} - {title}.{output-ext}")
            _, path = client.download(song)
            if path is None or not Path(path).is_file():
                details = (
                    client.downloader.errors[-1]
                    if client.downloader.errors
                    else "No matching audio source was available."
                )
                raise RuntimeError(f"spotDL could not download this track: {details}")
            emit(
                {
                    "event": "complete",
                    "index": index,
                    "file": str(path.resolve()),
                    "size": path.stat().st_size,
                }
            )
        except Exception as exc:
            emit({"event": "track_error", "index": index, "error": safe_error(exc)})


def main():
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    request = json.loads(sys.stdin.read())
    try:
        with contextlib.redirect_stdout(sys.stderr):
            run(request)
    except Exception as exc:
        emit({"event": "error", "error": safe_error(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
