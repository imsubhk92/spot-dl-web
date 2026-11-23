# Local core packages

This directory contains checksum-verified PyPI source distributions used directly by Side A. Original source, tests, metadata and license files are retained. The root `pyproject.toml` selects these packages through editable local paths; `uv.lock` records the resolution. Both native and Docker installations use these copies.

| Package | Upstream base | Local version | Changes |
| --- | --- | --- | --- |
| spotDL | 4.6.0 | 4.6.0+sidea.1 | Preserve playlist order; fail explicitly when any track metadata cannot be resolved |
| SpotipyFree | 1.9.15 | 1.9.15+sidea.1 | Cache public album, album-track, artist and song responses within a worker; return independent copies |
| SpotAPI | 1.2.8 | 1.2.8+sidea.1 | Share Spotify query catalogs by web-player build; persist public catalogs across workers; coordinate concurrent workers; bounded parallel static-file downloads; retry temporary read-only failures |
| yt-dlp | 2026.10.26 | 2026.10.26+sidea.1 | Local source and version identity; extractor behavior retained |
| ytmusicapi | 1.12.4 | 1.12.4+sidea.1 | Local source and explicit reproducible version; provider behavior retained |

`upstream.json` records the source URLs, original archive SHA-256 hashes, local versions, and patched-file hashes. `patches/side-a.patch` contains the changes against those original distributions. Original source archives downloaded during setup are in the ignored `.cache/` directory.

The public query cache lives under `data/cache/spotify-queries/`. It contains static JavaScript catalogs only. Authentication tokens, cookies and user metadata are excluded. Cache keys include the immutable Spotify web-player build URL; a new build generates a new entry. Invalid cache files are rebuilt, writes are atomic, and filesystem locks prevent duplicate builds in concurrent worker processes. Metadata-response caching stays in worker memory.

HTTP requests have bounded timeouts. Temporary 429/5xx responses are retried only for reads and known public metadata queries. Long rate-limit delays are surfaced to the caller. Mutation requests are not automatically retried for server response errors.

To change a core package, edit its source here. Restart the app after editing vendor files; the development reloader watches `app/` only. Run `make test`, `make smoke`, and the live album test before accepting a change. Reinstall with `make setup` after changing dependency metadata.

For an upgrade, review the upstream changes and license, obtain a new checksum-verified source archive, reapply only necessary patches, update versions and the provenance manifest, regenerate `uv.lock`, and rerun validation. Avoid replacing this directory through an unreviewed package upgrade. Transitive dependencies remain pinned in `uv.lock` and are installed normally; this directory is not a fully offline bundle of every transitive wheel.
