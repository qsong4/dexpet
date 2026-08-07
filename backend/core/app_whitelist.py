"""Configurable macOS app whitelist for open_app / close_app."""

from __future__ import annotations

from typing import Any

from backend.db.repository import Repository

SETTING_KEY = "app_whitelist"

DEFAULT_APP_ALIASES: dict[str, str] = {
    "safari": "Safari",
    "finder": "Finder",
    "terminal": "Terminal",
    "notes": "Notes",
    "mail": "Mail",
    "calendar": "Calendar",
    "music": "Music",
    "messages": "Messages",
    "photos": "Photos",
    "preview": "Preview",
    "maps": "Maps",
    "reminders": "Reminders",
    "system settings": "System Settings",
    "settings": "System Settings",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "vscode": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "cursor": "Cursor",
    "wechat": "WeChat",
    "微信": "WeChat",
    "netease": "NeteaseMusic",
    "netease music": "NeteaseMusic",
    "neteasemusic": "NeteaseMusic",
    "net ease music": "NeteaseMusic",
    "网易云": "NeteaseMusic",
    "网易云音乐": "NeteaseMusic",
    "云音乐": "NeteaseMusic",
    "网易音乐": "NeteaseMusic",
    "网易 云音乐": "NeteaseMusic",
}


def normalize_aliases(raw: Any) -> dict[str, str]:
    """Normalize mapping: lowercased alias -> app display name."""
    if not isinstance(raw, dict):
        return dict(DEFAULT_APP_ALIASES)
    out: dict[str, str] = {}
    for key, value in raw.items():
        alias = str(key).strip().lower()
        app = str(value).strip()
        if not alias or not app:
            continue
        out[alias] = app
    return out or dict(DEFAULT_APP_ALIASES)


def get_app_whitelist(repo: Repository) -> dict[str, str]:
    stored = repo.get_setting_json(SETTING_KEY, None)
    if stored is None:
        return dict(DEFAULT_APP_ALIASES)
    return normalize_aliases(stored)


def save_app_whitelist(repo: Repository, mapping: dict[str, str]) -> dict[str, str]:
    cleaned = normalize_aliases(mapping)
    repo.set_setting_json(SETTING_KEY, cleaned)
    return cleaned


def reset_app_whitelist(repo: Repository) -> dict[str, str]:
    return save_app_whitelist(repo, dict(DEFAULT_APP_ALIASES))


def whitelist_as_entries(mapping: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"alias": alias, "app": app}
        for alias, app in sorted(mapping.items(), key=lambda kv: (kv[1].lower(), kv[0]))
    ]


def entries_to_mapping(entries: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in entries:
        alias = str(item.get("alias") or "").strip().lower()
        app = str(item.get("app") or "").strip()
        if alias and app:
            mapping[alias] = app
    return mapping
