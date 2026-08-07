"""Safe macOS system helpers (no arbitrary shell)."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.core.app_whitelist import DEFAULT_APP_ALIASES

# Back-compat alias for imports/tests
APP_ALIASES = DEFAULT_APP_ALIASES

logger = logging.getLogger("dexpet.macos_system")

SHORTCUTS: dict[str, str] = {
    "spotlight": "spotlight",
    "screenshot": "screenshot",
    "screenshot_area": "screenshot_area",
}


def _run(args: list[str], *, input_text: str | None = None, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# Longer phrases first so「帮我打开」won't be partially mishandled.
_OPEN_PREFIXES = (
    "帮我打开",
    "请帮我打开",
    "麻烦打开",
    "请打开",
    "打开应用",
    "打开软件",
    "打开一下",
    "打开",
    "启动",
    "运行",
    "开启",
    "open the ",
    "open ",
    "launch ",
    "start ",
)

# Longer phrases first so「帮我关闭」won't be partially mishandled.
_CLOSE_PREFIXES = (
    "帮我关闭",
    "请帮我关闭",
    "麻烦关闭",
    "请关闭",
    "关闭应用",
    "关闭软件",
    "关闭一下",
    "关掉",
    "关闭",
    "帮我退出",
    "请帮我退出",
    "麻烦退出",
    "请退出",
    "退出应用",
    "退出软件",
    "退出一下",
    "退出",
    "quit the ",
    "quit ",
    "close the ",
    "close ",
)

_APP_VERB_PREFIXES = _CLOSE_PREFIXES + _OPEN_PREFIXES


def _compact_app_key(value: str) -> str:
    """Collapse whitespace/punct so『网易 云音乐』matches『网易云音乐』."""
    key = value.strip().lower()
    key = re.sub(r"[\s\u3000_\-·.•]+", "", key)
    if key.endswith(".app"):
        key = key[:-4]
    return key


def _normalize_app_query(name: str) -> str:
    key = name.strip().lower()
    # strip surrounding quotes
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "'\"":
        key = key[1:-1].strip()
    changed = True
    while changed and key:
        changed = False
        for prefix in _APP_VERB_PREFIXES:
            if key.startswith(prefix):
                key = key[len(prefix) :].strip(" ：:，,。.!！")
                changed = True
                break
    return _compact_app_key(key)


def resolve_app_name(name: str, aliases: dict[str, str] | None = None) -> str | None:
    mapping = aliases if aliases is not None else DEFAULT_APP_ALIASES
    key = _normalize_app_query(name)
    if not key:
        return None

    compact_map: dict[str, str] = {}
    for alias, app in mapping.items():
        compact_map.setdefault(_compact_app_key(alias), app)
        compact_map.setdefault(_compact_app_key(app), app)

    if key in compact_map:
        return compact_map[key]

    # Longest alias / app-name substring match (handles noisy LLM args)
    best_alias = ""
    best_app: str | None = None
    for cand, app in compact_map.items():
        if len(cand) < 2:
            continue
        if cand in key or key in cand:
            if len(cand) > len(best_alias):
                best_alias = cand
                best_app = app
    return best_app


def open_app(name: str, aliases: dict[str, str] | None = None) -> dict[str, Any]:
    mapping = aliases if aliases is not None else DEFAULT_APP_ALIASES
    normalized = _normalize_app_query(name)
    app = resolve_app_name(name, mapping)
    logger.info(
        "open_app raw=%r normalized=%r resolved=%r",
        name,
        normalized,
        app,
    )
    if not app:
        return {
            "ok": False,
            "error": f"应用不在白名单：{name}",
            "raw": name,
            "normalized": normalized,
            "allowed": sorted(set(mapping.values())),
        }
    proc = _run(["open", "-a", app])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "打开失败").strip()
        logger.warning("open_app failed app=%r error=%r", app, err)
        return {"ok": False, "error": err, "app": app, "raw": name, "normalized": normalized}
    logger.info("open_app ok app=%r", app)
    return {"ok": True, "app": app, "raw": name, "normalized": normalized}


def close_app(name: str, aliases: dict[str, str] | None = None) -> dict[str, Any]:
    mapping = aliases if aliases is not None else DEFAULT_APP_ALIASES
    normalized = _normalize_app_query(name)
    app = resolve_app_name(name, mapping)
    logger.info(
        "close_app raw=%r normalized=%r resolved=%r",
        name,
        normalized,
        app,
    )
    if not app:
        return {
            "ok": False,
            "error": f"应用不在白名单：{name}",
            "raw": name,
            "normalized": normalized,
            "allowed": sorted(set(mapping.values())),
        }
    # Prefer AppleScript quit over kill — lets the app save/exit cleanly.
    safe_app = app.replace("\\", "\\\\").replace('"', '\\"')
    proc = _run(["osascript", "-e", f'quit app "{safe_app}"'])
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "关闭失败").strip()
        logger.warning("close_app failed app=%r error=%r", app, err)
        return {"ok": False, "error": err, "app": app, "raw": name, "normalized": normalized}
    logger.info("close_app ok app=%r", app)
    return {"ok": True, "app": app, "raw": name, "normalized": normalized}


def open_url(url: str) -> dict[str, Any]:
    raw = url.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "error": "仅允许 http/https URL"}
    proc = _run(["open", raw])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "打开失败").strip()}
    return {"ok": True, "url": raw}


def _is_safe_path(path: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return False
    home = Path.home().resolve()
    tmp = Path("/tmp").resolve()
    allowed_roots = (home, tmp)
    return any(resolved == root or root in resolved.parents for root in allowed_roots)


def open_path(path: str) -> dict[str, Any]:
    target = Path(path).expanduser()
    if not _is_safe_path(target):
        return {"ok": False, "error": "路径不在允许范围内（仅用户目录或 /tmp）"}
    if not target.exists():
        return {"ok": False, "error": f"路径不存在：{target}"}
    proc = _run(["open", str(target.resolve())])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "打开失败").strip()}
    return {"ok": True, "path": str(target.resolve())}


def clipboard_get() -> dict[str, Any]:
    proc = _run(["pbpaste"])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "读取剪贴板失败").strip()}
    text = proc.stdout
    # Cap size for LLM context
    truncated = False
    if len(text) > 4000:
        text = text[:4000]
        truncated = True
    return {"ok": True, "text": text, "truncated": truncated}


def clipboard_set(text: str) -> dict[str, Any]:
    proc = _run(["pbcopy"], input_text=text)
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "写入剪贴板失败").strip()}
    return {"ok": True, "length": len(text)}


def volume_get() -> dict[str, Any]:
    proc = _run(
        ["osascript", "-e", "output volume of (get volume settings)"]
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "读取音量失败").strip()}
    try:
        level = int(proc.stdout.strip())
    except ValueError:
        return {"ok": False, "error": f"无法解析音量：{proc.stdout!r}"}
    return {"ok": True, "volume": level}


def volume_set(level: int) -> dict[str, Any]:
    value = max(0, min(100, int(level)))
    proc = _run(["osascript", "-e", f"set volume output volume {value}"])
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "设置音量失败").strip()}
    return {"ok": True, "volume": value}


def set_dnd(enabled: bool) -> dict[str, Any]:
    # Best-effort: toggle Focus via Shortcuts / Control Center shortcut (needs Accessibility).
    # Prefer `shortcuts` if a user shortcut exists; else try menu bar Focus.
    script_on = (
        'tell application "System Events" to keystroke "d" using {command down, option down}'
    )
    # Option+Cmd+D is usually Dock hide — not DND.
    # Use Focus keyboard: many setups use Control Center; try shortcuts run.
    shortcut_name = "Set Focus" if enabled else "Turn Off Focus"
    proc = _run(["shortcuts", "run", shortcut_name], timeout=12.0)
    if proc.returncode == 0:
        return {
            "ok": True,
            "enabled": enabled,
            "method": "shortcuts",
            "note": f"已运行快捷指令「{shortcut_name}」",
        }
    # Fallback: open Focus settings so user can toggle
    _run(["open", "x-apple.systempreferences:com.apple.Focus-Settings.extension"])
    return {
        "ok": False,
        "enabled": enabled,
        "error": (
            "无法自动切换勿扰/专注模式。请在「快捷指令」中创建名为 "
            f"「{'Set Focus' if enabled else 'Turn Off Focus'}」的指令，或手动在系统设置中切换。"
        ),
        "opened_settings": True,
    }


def lock_screen() -> dict[str, Any]:
    # CGSession is reliable on Intel/older; on Apple Silicon use loginwindow.
    candidates = [
        [
            "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession",
            "-suspend",
        ],
        ["pmset", "displaysleepnow"],
        [
            "osascript",
            "-e",
            'tell application "System Events" to keystroke "q" using {control down, command down}',
        ],
    ]
    errors: list[str] = []
    for args in candidates:
        proc = _run(args, timeout=5.0)
        if proc.returncode == 0:
            return {"ok": True, "method": args[0]}
        errors.append((proc.stderr or proc.stdout or str(args)).strip())
    return {"ok": False, "error": "锁屏失败", "detail": errors[:3]}


def trigger_shortcut(name: str) -> dict[str, Any]:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in SHORTCUTS:
        return {
            "ok": False,
            "error": f"快捷操作不在白名单：{name}",
            "allowed": sorted(SHORTCUTS.keys()),
        }
    action = SHORTCUTS[key]
    if action == "spotlight":
        script = 'tell application "System Events" to keystroke space using {command down}'
    elif action == "screenshot":
        script = 'tell application "System Events" to keystroke "5" using {command down, shift down}'
    else:  # screenshot_area
        script = 'tell application "System Events" to keystroke "4" using {command down, shift down}'
    proc = _run(["osascript", "-e", script])
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or "需要辅助功能权限才能模拟快捷键").strip(),
            "action": action,
        }
    return {"ok": True, "action": action}
