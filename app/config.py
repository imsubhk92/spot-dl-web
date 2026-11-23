import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def data_dir() -> Path:
    path = Path(os.environ.get("SPOTDL_DATA_DIR", str(ROOT / "data"))).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def worker_env(root: Path, public_cache: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    # Isolate upstream caches, credentials and temporary media from the user's home.
    home = root / "worker-home"
    home.mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"), PYTHONUNBUFFERED="1")
    env["PYTHONPATH"] = str(ROOT)
    if public_cache is not None:
        env["SPOTAPI_CACHE_DIR"] = str(public_cache)
    if env.get("SPOTDL_COOKIE_FILE"):
        env["SPOTDL_COOKIE_FILE"] = str(Path(env["SPOTDL_COOKIE_FILE"]).resolve())
    return env
