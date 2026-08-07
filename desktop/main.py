"""Desktop entrypoint."""

from __future__ import annotations

from desktop.window import run_window


def run() -> None:
    run_window()


if __name__ == "__main__":
    run()
