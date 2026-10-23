#!/usr/bin/env python3
"""
Launcher for the MedBox backend.

Why this exists
----------------
Every module under backend/ imports using the full package path, e.g.:

    from backend.database import init_db

That only resolves if Python's working directory / sys.path root is THIS
file's directory (project/), the parent of backend/ -- so that "backend"
itself is importable as a top-level package. Running things like

    cd backend && uvicorn main:app --reload
    cd backend && python main.py

fails with:

    ModuleNotFoundError: No module named 'backend'

This script can be invoked from ANYWHERE (it pins sys.path itself), so it
always launches the app the same, correct way. Usage:

    python run_backend.py
    python run_backend.py --reload
    python run_backend.py --host 0.0.0.0 --port 8000

Any extra CLI args are forwarded to uvicorn.
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    # Make sure "backend" resolves as a package no matter where this
    # script was launched from.
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    os.chdir(PROJECT_ROOT)

    import uvicorn

    args = sys.argv[1:]
    host = "127.0.0.1"
    port = 8000
    reload = False

    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        elif args[i] == "--reload":
            reload = True
            i += 1
        else:
            i += 1

    if not os.environ.get("GROQ_API_KEY"):
        print(
            "Note: GROQ_API_KEY is not set. The app will still start, "
            "but the AI voice assistant (/api/agent/chat) will respond with "
            "a 'not configured yet' message instead of talking to the AI.\n"
            "Get a free key at https://console.groq.com and set it:\n"
            "  $env:GROQ_API_KEY='gsk_...'\n",
            file=sys.stderr,
        )

    uvicorn.run("backend.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
