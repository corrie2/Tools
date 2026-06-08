#!/usr/bin/env python3
"""Start the local Agent Long Memory monitor."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_ROOT / "src"))


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_dotenv(PACKAGE_ROOT / ".env")

    parser = argparse.ArgumentParser(description="Start the Agent Long Memory monitor")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8081, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")
    args = parser.parse_args()

    try:
        import uvicorn
        from agent_long_memory.monitor_api import app
    except ImportError as exc:
        print(f"Missing monitor dependency: {exc}")
        print("Install with: pip install -e .")
        sys.exit(1)

    print("Starting Agent Long Memory monitor")
    print(f"URL: http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
