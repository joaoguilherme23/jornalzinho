"""Entrada local: python -m app.run --reload (Psycopg no Windows)."""

import argparse
import asyncio
import sys

import uvicorn


def selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Jornalzinho: FastAPI + React")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run(
        "app.main:aplicacao", host=args.host, port=args.port, reload=args.reload,
        loop="app.run:selector_loop" if sys.platform == "win32" else "auto",
        access_log=False, proxy_headers=False,
    )


if __name__ == "__main__":
    main()
