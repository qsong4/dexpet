"""Keychain helpers for per-profile API keys, with file fallback.

macOS Keychain writes fail under some environments (e.g. Cursor seatbelt
sandbox → keyring error 100001). When that happens we persist keys under
Application Support so settings «保存模型» still succeeds.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import keyring

from backend.paths import KEYCHAIN_SERVICE, KEYCHAIN_USERNAME, data_dir

logger = logging.getLogger(__name__)

ProfileName = str  # "deepseek" | "custom" | uuid


def _username(profile: ProfileName | None = None) -> str:
    if not profile:
        return KEYCHAIN_USERNAME
    return f"{KEYCHAIN_USERNAME}_{profile}"


def _file_store_path() -> Path:
    return data_dir() / "secrets" / "api_keys.json"


def _read_file_store() -> dict[str, str]:
    path = _file_store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def _write_file_store(store: dict[str, str]) -> None:
    path = _file_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _set_file_key(username: str, api_key: str) -> None:
    store = _read_file_store()
    store[username] = api_key
    _write_file_store(store)


def _clear_file_key(username: str) -> None:
    store = _read_file_store()
    if username not in store:
        return
    del store[username]
    if store:
        _write_file_store(store)
    else:
        path = _file_store_path()
        path.unlink(missing_ok=True)


def _get_file_key(username: str) -> str | None:
    return _read_file_store().get(username)


def get_api_key(profile: ProfileName | None = None) -> str | None:
    """Get key for a profile. Legacy single-key slot used only when profile is None."""
    username = _username(profile) if profile else KEYCHAIN_USERNAME
    try:
        value = keyring.get_password(KEYCHAIN_SERVICE, username)
        if value:
            return value
    except Exception:  # noqa: BLE001 — Keychain may be locked / sandboxed
        logger.debug("keyring get_password failed for %s", username, exc_info=True)
    return _get_file_key(username)


def set_api_key(api_key: str, profile: ProfileName | None = None) -> None:
    usernames = [_username(profile)]
    if profile is not None:
        # Keep legacy slot in sync with whatever was last written (compat).
        usernames.append(KEYCHAIN_USERNAME)

    try:
        for name in usernames:
            keyring.set_password(KEYCHAIN_SERVICE, name, api_key)
    except Exception as exc:  # noqa: BLE001 — PasswordSetError / sandbox / ACL
        logger.warning(
            "Keychain write failed (%s); storing API key in local file fallback",
            exc,
        )
        for name in usernames:
            _set_file_key(name, api_key)
        return

    # Prefer Keychain as source of truth; drop stale file copies.
    for name in usernames:
        _clear_file_key(name)


def delete_api_key(profile: ProfileName | None = None) -> None:
    username = _username(profile)
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, username)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("keyring delete_password failed for %s", username, exc_info=True)
    _clear_file_key(username)
