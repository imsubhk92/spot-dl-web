"""Run both development servers; stop their process groups together on Ctrl+C."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
children = []


def main():
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--reload",
                    "--reload-dir",
                    str(ROOT / "app"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8002",
                ],
                cwd=ROOT,
                start_new_session=True,
            )
        )
        children.append(
            subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "frontend", start_new_session=True)
        )
        print("\nSide A → http://127.0.0.1:5173\nAPI docs → http://127.0.0.1:8002/docs\n", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=7)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)


if __name__ == "__main__":
    main()
