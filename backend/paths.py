"""Application paths and constants."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "DexPet"
KEYCHAIN_SERVICE = "dexpet"
KEYCHAIN_USERNAME = "llm_api_key"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("DEXPET_PORT", "8765"))
WS_PATH = "/ws"

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


def data_dir() -> Path:
    path = Path.home() / "Library" / "Application Support" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "dexpet.db"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def sprites_dir() -> Path:
    path = data_dir() / "sprites"
    path.mkdir(parents=True, exist_ok=True)
    return path


def memory_dir() -> Path:
    path = data_dir() / "memory"
    path.mkdir(parents=True, exist_ok=True)
    (path / "daily").mkdir(parents=True, exist_ok=True)
    return path
