# Side A · Spotify Downloader

A personal, local music downloader with a **FastAPI server**, **Vite + React + TypeScript frontend**, and **[spotDL](https://github.com/spotdl/spotify-downloader)** as the download engine.

Paste a public Spotify track, album, or playlist URL, preview its tracks, choose what to download, and save audio with artwork and metadata. Play completed tracks in the browser, download individual files, or get a collection as a ZIP.

## Run locally

Prerequisites: **uv**, **Node.js 22.12+** (24 recommended), and **FFmpeg** on your PATH. `uv` installs Python 3.13 inside this project. The project's local `.tools/node/bin` is used when present; otherwise Make uses your system Node installation.

```sh
make setup
make dev
```

- Frontend: **http://127.0.0.1:5173**
- API and Swagger documentation: **http://127.0.0.1:8002/docs**

`make dev` runs both servers with reload. Ctrl+C stops both. Port 8002 keeps this app separate from other local downloaders. Vite proxies `/api` requests to FastAPI.

To serve the built React app directly through FastAPI:

```sh
make build
make run
```

Open **http://127.0.0.1:8002**. This is also the single-port production build used by Docker.

## Features

- Public Spotify songs, albums, playlists, and Spotify URIs; international and shared links are normalized.
- Track preview and selection before downloading; limit of 1,000 tracks per preview.
- MP3, M4A, Opus, and FLAC output with optional encoding bitrate.
- Persistent SQLite queue, track progress, history, and download defaults.
- One active collection at a time; up to 50 queued collections; preview requests run separately.
- Cancellation terminates the worker's process group, including its FFmpeg process.
- Failed and cancelled collections can be retried; completed tracks are retained.
- Interrupted jobs are marked after a server restart and can be explicitly retried.
- Browser playback with HTTP range requests, individual downloads, and ZIP archives of completed tracks.
- Searchable library, download filters, and persistent light/dark appearance.
- Local font assets and runtime diagnostics; no frontend CDN dependency.
- Deletion removes both the download history entry and its audio files after confirmation.

## Spotify and YouTube configuration

spotDL reads Spotify metadata and finds matching audio on **YouTube / YouTube Music**. It does not extract Spotify's audio. Output bitrate and FLAC conversion cannot improve the original source quality; matches may differ from the original Spotify recording.

Public metadata uses the local patched spotDL 4.6 client. Core source copies of spotDL, SpotipyFree, SpotAPI, yt-dlp and ytmusicapi live in [`vendor/`](vendor/README.md), with original licenses, source checksums, local version identifiers and reviewable patches. `uv` and Docker both install these copies.

The Spotify client shares query definitions by Spotify web-player build, persists public query catalogs across workers, reuses album/artist metadata, and retries temporary metadata failures. Incomplete track metadata produces an explicit error instead of silently omitting tracks. Optional server configuration:

```sh
cp .env.example .env
```

```dotenv
SPOTDL_DATA_DIR=./data
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTDL_COOKIE_FILE=
SPOTDL_PREVIEW_TIMEOUT=180
SPOTDL_DOWNLOAD_TIMEOUT=7200
```

Providing both Spotify credentials enables spotDL's official Spotify API mode. Use credentials from your Spotify developer application. No credentials are sent to the React app or saved in job history. This application handles public links; interactive OAuth/private playlists are outside its current scope.

`SPOTDL_COOKIE_FILE` can point to a Netscape-format YouTube cookies file when YouTube requires authentication. Workers use private copies so yt-dlp cannot modify your original file. Keep `.env` and cookie files private. Restart the server after changing environment configuration.

Spotify's default metadata client depends on Spotify's web service and can time out or change independently of this app. Official API mode may help when it is unavailable. YouTube can also impose authentication, geographic restrictions, or rate limits. The UI surfaces timeouts and track errors; retry preserves successful tracks.

Node is explicitly enabled as yt-dlp's JavaScript runtime. Deno is also supported when installed and Node is absent. The installed spotDL dependency includes yt-dlp's EJS support.

Use downloads for content you own or have permission to download. This project is independent of Spotify.

## Data and deployment

Native data stays in `data/` until explicitly deleted: `library.sqlite3` contains jobs, previews, and preferences; `downloads/<job-id>/` contains audio. Public Spotify query catalogs are cached in `cache/spotify-queries/` under that same directory; these contain static JavaScript only. Worker homes and temporary media remain isolated and are cleaned up after exit. SQLite uses WAL mode. Stop the app before copying the data directory for a simple backup.

Run a **single Uvicorn worker**. An exclusive filesystem lock rejects concurrent servers using the same data directory. The queue is in-process, while job state is persisted. Hard restarts require manual retry of interrupted downloads. A timeout applies to the whole collection, including all selected tracks.

This is a localhost application with no account system. The standard commands and Compose bind to loopback. Host and mutation-origin checks protect the local API. Add authentication and a suitable reverse proxy before adapting it for shared or remote use. ZIP creation requires enough free disk space for a temporary archive.

## Docker

```sh
make docker-up
# http://127.0.0.1:8002
make docker-down
```

Stop the native server first if it uses port 8002. Compose stores its data in the `music` named volume, independently from native `data/`, and preserves it when stopped. The container runs as an unprivileged user with FFmpeg and Node, a health check, and `restart: unless-stopped`. `docker compose down -v` deletes that volume and its downloads.

Compose reads optional Spotify credentials from `.env`. To use cookies in Docker, add a read-only bind mount for your cookie file and set `SPOTDL_COOKIE_FILE` to its container path.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Engine version and dependency/configuration checks |
| POST | `/api/preview` | Resolve `{ "url": "https://open.spotify.com/…" }` |
| GET / POST | `/api/jobs` | List or create a download |
| GET / DELETE | `/api/jobs/{id}` | Read or delete a download and files |
| POST | `/api/jobs/{id}/cancel` | Stop an active download |
| POST | `/api/jobs/{id}/retry` | Queue unfinished tracks again |
| GET | `/api/jobs/{id}/tracks/{index}/file` | Save audio (`?inline=true` for playback) |
| GET | `/api/jobs/{id}/zip` | Archive completed tracks |
| GET / PUT | `/api/preferences` | Persistent format/bitrate defaults |

Create a download using the returned preview ID and zero-based track indices:

```json
{
  "preview_id": "<preview-id>",
  "indices": [0, 2, 3],
  "format": "mp3",
  "bitrate": "auto"
}
```

The server uses its stored metadata for the selected tracks. Clients cannot submit arbitrary commands, audio URLs, output paths, or downloaded file paths. Progress is polled by the frontend every 1.8 seconds. Failures can occur per track, producing a partially completed collection.

## Validation

```sh
make test                 # backend behavior and frontend API tests
make check                # verify vendor paths/hashes, Python lint/format, TypeScript/Vite build
make smoke                # real spotDL/FFmpeg using generated local audio
```

The smoke test creates temporary local audio, downloads it through the real spotDL child process, verifies MP3/M4A/Opus/FLAC codecs and title/artist metadata, tests playback ranges and ZIP contents, and deletes its temporary downloads. It does not use external music or modify your library.

Browser tests use deterministic API responses and require a running built app at port 8002:

```sh
make browser-setup
make e2e
```

They cover playlist selection, queue submission, library search, dark-mode ZIP download, deletion confirmation, saved settings, theme persistence, preview errors, and mobile layout.

Verification passed **41 backend/vendor tests, 5 frontend tests, 4 browser tests**, local-package source/hash checks, Python lint/format checks, and the TypeScript/Vite production build. The real audio smoke test passed for all four output formats. The Docker image uses the local source packages.

Live verification with `https://open.spotify.com/album/7xLyQXqKOix3czQCjrc1tF` resolved all **12 tracks in 32.5 seconds**, then **19.2 seconds** in a fresh worker using the persisted cache. A real MP3 of **Jupiter — Brodinski** downloaded in about **20 seconds**. FFprobe verified its codec, duration, title/artist tags and embedded artwork. HTTP ranges, ZIP contents, persistence across a server restart, and playback in the React library were verified. Test media is excluded from this repository. These results verify that album and one live track; provider availability and other collections can still vary.

## Layout

```text
app/          FastAPI routes, SQLite store, queue, isolated spotDL bridge
frontend/     Vite/React UI, unit tests, Playwright browser tests
scripts/      Development supervisor and real audio integration smoke test
tests/        API, queue, persistence, cancellation and file-serving tests
vendor/       Reviewed local core sources, licenses, provenance and patches
```
