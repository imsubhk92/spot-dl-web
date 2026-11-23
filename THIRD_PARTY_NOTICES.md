# Third-party sources and notices

Side A includes local copies of the following upstream packages. Each package retains its own license, copyright notices and source files. See `vendor/upstream.json` for source archive URLs, checksums and the exact local modifications, and `vendor/patches/side-a.patch` for the patch set.

| Component | License | Included notice |
| --- | --- | --- |
| spotDL 4.6.0 | MIT | `vendor/spotdl/LICENSE` |
| SpotipyFree 1.9.15 | MIT | `vendor/spotipyfree/LICENSE` |
| SpotAPI 1.2.8 | GNU GPL version 3 | `vendor/spotapi/LICENSE` |
| yt-dlp 2026.10.26 | Unlicense; additional upstream notices apply to included code | `vendor/yt-dlp/LICENSE` and upstream source notices |
| ytmusicapi 1.12.4 | MIT | `vendor/ytmusicapi/LICENSE` |
| DM Sans | SIL Open Font License 1.1 | `frontend/public/fonts/dmsans-LICENSE.txt` |
| Manrope | SIL Open Font License 1.1 | `frontend/public/fonts/manrope-LICENSE.txt` |

Local package versions use the `+sidea.1` suffix. SpotAPI's local modifications were made on 2026-11-23 and are identified in its modified source files. Public Spotify query caching, bounded requests and retries are part of these local modifications.

The vendored sources include upstream test certificates, sample keys and public extractor defaults. These are retained copies from the published source distributions. Personal environment files, cookies, downloaded media, database contents and runtime caches are excluded from version control.
