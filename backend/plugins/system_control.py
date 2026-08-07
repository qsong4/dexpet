"""macOS system control plugin (whitelisted actions)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from backend.core import macos_system as mac
from backend.core import webpage
from backend.core.app_whitelist import get_app_whitelist
from backend.core.tools import Plugin, ToolSpec
from backend.db.repository import Repository

logger = logging.getLogger("dexpet.system_control")

AlwaysOnTopNotifier = Callable[[bool], None]


class SystemControlPlugin(Plugin):
    name = "system"

    def __init__(
        self,
        repo: Repository,
        on_always_on_top: AlwaysOnTopNotifier | None = None,
    ) -> None:
        self.repo = repo
        self.on_always_on_top = on_always_on_top

    def set_always_on_top_notifier(self, cb: AlwaysOnTopNotifier | None) -> None:
        self.on_always_on_top = cb

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="open_app",
                description=(
                    "打开白名单内的 macOS 应用。"
                    "name 只填应用名或别名（如 网易云音乐、Safari），不要带「打开」等动词。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "应用名或别名，例如 网易云音乐 / Safari / WeChat",
                        },
                    },
                    "required": ["name"],
                },
                handler=self.open_app,
            ),
            ToolSpec(
                name="close_app",
                description=(
                    "关闭/退出白名单内的 macOS 应用（AppleScript quit，非强制 kill）。"
                    "用户说关闭、退出某应用时调用。"
                    "name 只填应用名或别名（如 网易云音乐、Safari），不要带「关闭/退出」等动词。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "应用名或别名，例如 网易云音乐 / Safari / WeChat",
                        },
                    },
                    "required": ["name"],
                },
                handler=self.close_app,
            ),
            ToolSpec(
                name="open_url",
                description="用默认浏览器打开 http/https 链接。",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL"},
                    },
                    "required": ["url"],
                },
                handler=self.open_url,
            ),
            ToolSpec(
                name="fetch_url",
                description=(
                    "拉取公开网页并抽取正文（不执行 JS）。"
                    "用户要求总结/阅读某个链接时必须调用此工具，不要假装已读页面。"
                    "仅支持 http/https；拒绝内网与本机地址。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "要读取的 http/https URL",
                        },
                    },
                    "required": ["url"],
                },
                handler=self.fetch_url,
            ),
            ToolSpec(
                name="open_path",
                description="打开用户目录或 /tmp 下的文件/文件夹。",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "本地路径"},
                    },
                    "required": ["path"],
                },
                handler=self.open_path,
            ),
            ToolSpec(
                name="clipboard_get",
                description="读取剪贴板文本。",
                parameters={"type": "object", "properties": {}},
                handler=self.clipboard_get,
            ),
            ToolSpec(
                name="clipboard_set",
                description="写入剪贴板文本。",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "要写入的文本"},
                    },
                    "required": ["text"],
                },
                handler=self.clipboard_set,
            ),
            ToolSpec(
                name="volume_get",
                description="查询当前输出音量（0-100）。",
                parameters={"type": "object", "properties": {}},
                handler=self.volume_get,
            ),
            ToolSpec(
                name="volume_set",
                description="设置输出音量（0-100）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "level": {"type": "integer", "description": "音量 0-100"},
                    },
                    "required": ["level"],
                },
                handler=self.volume_set,
            ),
            ToolSpec(
                name="set_dnd",
                description="尝试开启/关闭勿扰或专注模式（依赖快捷指令，可能需用户授权）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "description": "true=开启，false=关闭"},
                    },
                    "required": ["enabled"],
                },
                handler=self.set_dnd,
            ),
            ToolSpec(
                name="lock_screen",
                description="锁定屏幕。",
                parameters={"type": "object", "properties": {}},
                handler=self.lock_screen,
            ),
            ToolSpec(
                name="trigger_shortcut",
                description="触发白名单系统快捷操作：spotlight / screenshot / screenshot_area。",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": ["spotlight", "screenshot", "screenshot_area"],
                        },
                    },
                    "required": ["name"],
                },
                handler=self.trigger_shortcut,
            ),
            ToolSpec(
                name="set_always_on_top",
                description="设置宠物窗口是否始终置顶（浮在其他窗口之上）。",
                parameters={
                    "type": "object",
                    "properties": {
                        "enabled": {
                            "type": "boolean",
                            "description": "true=始终置顶，false=不强制置顶",
                        },
                    },
                    "required": ["enabled"],
                },
                handler=self.set_always_on_top,
            ),
            ToolSpec(
                name="get_always_on_top",
                description="查询宠物是否始终置顶。",
                parameters={"type": "object", "properties": {}},
                handler=self.get_always_on_top,
            ),
        ]

    def open_app(self, name: str) -> dict[str, Any]:
        aliases = get_app_whitelist(self.repo)
        logger.info("tool open_app name=%r whitelist_size=%d", name, len(aliases))
        result = mac.open_app(name, aliases=aliases)
        logger.info("tool open_app result=%s", result)
        return result

    def close_app(self, name: str) -> dict[str, Any]:
        aliases = get_app_whitelist(self.repo)
        logger.info("tool close_app name=%r whitelist_size=%d", name, len(aliases))
        result = mac.close_app(name, aliases=aliases)
        logger.info("tool close_app result=%s", result)
        return result

    def open_url(self, url: str) -> dict[str, Any]:
        return mac.open_url(url)

    def fetch_url(self, url: str) -> dict[str, Any]:
        logger.info("tool fetch_url url=%r", url)
        result = webpage.fetch_url(url)
        logger.info(
            "tool fetch_url ok=%s truncated=%s",
            result.get("ok"),
            result.get("truncated"),
        )
        return result

    def open_path(self, path: str) -> dict[str, Any]:
        return mac.open_path(path)

    def clipboard_get(self) -> dict[str, Any]:
        return mac.clipboard_get()

    def clipboard_set(self, text: str) -> dict[str, Any]:
        return mac.clipboard_set(text)

    def volume_get(self) -> dict[str, Any]:
        return mac.volume_get()

    def volume_set(self, level: int) -> dict[str, Any]:
        return mac.volume_set(level)

    def set_dnd(self, enabled: bool) -> dict[str, Any]:
        return mac.set_dnd(bool(enabled))

    def lock_screen(self) -> dict[str, Any]:
        return mac.lock_screen()

    def trigger_shortcut(self, name: str) -> dict[str, Any]:
        return mac.trigger_shortcut(name)

    def get_always_on_top(self) -> dict[str, Any]:
        raw = self.repo.get_pet_state("always_on_top", "1")
        enabled = raw != "0"
        return {"ok": True, "always_on_top": enabled}

    def set_always_on_top(self, enabled: bool) -> dict[str, Any]:
        flag = bool(enabled)
        self.repo.set_pet_state("always_on_top", "1" if flag else "0")
        if self.on_always_on_top is not None:
            try:
                self.on_always_on_top(flag)
            except Exception:  # noqa: BLE001
                pass
        return {
            "ok": True,
            "always_on_top": flag,
            "message": "已开启始终置顶" if flag else "已关闭始终置顶",
        }
