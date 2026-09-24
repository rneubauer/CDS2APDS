"""Run the link service: ``python -m cds_apds_link`` (configuration via environment variables)."""
from __future__ import annotations

import logging
import os
import sys

import uvicorn

from .app import create_app
from .config import Settings


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        settings = Settings.from_env(os.environ)
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    # Access logs are off: request lines can carry identifiers that must not be logged.
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
