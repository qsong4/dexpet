"""Backend entrypoint."""

from __future__ import annotations

import logging

import uvicorn

from backend.app import create_app
from backend.paths import DEFAULT_HOST, DEFAULT_PORT


def _configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s:%(name)s:%(message)s",
        )
    logging.getLogger("dexpet").setLevel(logging.INFO)


def run() -> None:
    _configure_logging()
    app = create_app()
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    run()
