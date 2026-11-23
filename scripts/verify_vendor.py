"""Verify that core imports come from the reviewed local sources."""

import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = {
    "spotdl": "spotdl",
    "spotipyfree": "SpotipyFree",
    "spotapi": "spotapi",
    "yt-dlp": "yt_dlp",
    "ytmusicapi": "ytmusicapi",
}


def main():
    manifest = json.loads((ROOT / "vendor" / "upstream.json").read_text())
    for name, module in MODULES.items():
        source = ROOT / "vendor" / name
        imported = Path(importlib.import_module(module).__file__).resolve()
        assert imported.is_relative_to(source), f"{name} loaded from unexpected path: {imported}"
        version = importlib.metadata.version(name)
        assert version == manifest[name]["local_version"], (name, version)
        for path, expected in manifest[name]["patched_files_sha256"].items():
            assert hashlib.sha256((source / path).read_bytes()).hexdigest() == expected, (
                f"Unrecorded vendor change: {name}/{path}"
            )
        print(f"PASS {name} {version}: local source and patch hashes")


if __name__ == "__main__":
    main()
