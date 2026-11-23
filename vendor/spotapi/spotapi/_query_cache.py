# Side A local modifications, 2026-11-23: shared public query caching and bounded requests.
# This file is distributed under the upstream SpotAPI GPLv3 license; see vendor/spotapi/LICENSE.
"""Side A patch: share public JS catalogs by Spotify build, never authentication data."""
import contextlib
import fcntl
import gzip
import hashlib
import os
import tempfile
import threading
from pathlib import Path

_memory = {}
_lock = threading.RLock()


def catalog(build_url, loader):
    with _lock:
        if build_url in _memory:
            return _memory[build_url]
        cache_dir = os.getenv("SPOTAPI_CACHE_DIR")
        if not cache_dir:
            value = loader()
            _memory[build_url] = value
            return value
        root = Path(cache_dir)
        root.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(build_url.encode()).hexdigest()
        path = root / (key + ".txt.gz")
        # A second preview process waits for the first build instead of downloading again.
        with (root / (key + ".lock")).open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                value = gzip.decompress(path.read_bytes()).decode()
                if not value:
                    raise ValueError("Empty cache")
            except (OSError, EOFError, ValueError, UnicodeError):
                value = loader()
                fd, temp = tempfile.mkstemp(dir=root, prefix=key, suffix=".tmp")
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(gzip.compress(value.encode()))
                    os.replace(temp, path)
                finally:
                    with contextlib.suppress(FileNotFoundError):
                        os.unlink(temp)
            _memory[build_url] = value
            while len(_memory) > 4:
                del _memory[next(iter(_memory))]
            return value
