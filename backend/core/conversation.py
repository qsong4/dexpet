"""Conversation manager: history, emotion, LLM, tools, memory."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Callable, Awaitable
from typing import Any

from datetime import datetime

from backend.core.emotion import Emotion, EmotionStateMachine
from backend.core.history import build_context_messages, maybe_summarize_session
from backend.core.llm.openai_compatible import OpenAICompatibleClient
from backend.core.memory import add_memory, format_memory_block, search_memory
from backend.core.memory_files import format_file_memory_block
from backend.core.tools import ToolRouter
from backend.db.repository import Repository

logger = logging.getLogger("dexpet.conversation")

SYSTEM_PERSONA = """你是 DexPet，一只生活在 macOS 桌面上的可爱猫咪助手。
用简洁友好的中文回答。若需要设置提醒，请调用工具 create_reminder。
设置相对提醒（如「一分钟后」「5分钟后」）时，必须使用 delay_seconds（秒），不要猜年份。
只有用户明确给出日期时间时才用 fire_at，且年份必须正确。
查询 A 股行情时调用 query_stock；监控股价/涨跌幅时调用 watch_stock。
系统操作（打开/关闭应用、链接、音量、剪贴板、锁屏、置顶等）请调用对应 system 工具，不要编造已执行。
用户说关闭或退出某应用时调用 close_app；打开应用用 open_app。
用户给出网页链接并要求总结/阅读时，必须调用 fetch_url 拉取正文后再回答；不要假装已经读过页面。open_url 只负责在浏览器中打开，不返回内容。
在回复末尾追加情绪标签，格式严格为 [[emotion:happy]]（可选值：happy/curious/sad/surprised/idle）。
"""


class ConversationManager:
    def __init__(
        self,
        repo: Repository,
        llm: OpenAICompatibleClient,
        emotion: EmotionStateMachine,
        tools: ToolRouter,
        on_emotion: Callable[[Emotion], Awaitable[None] | None] | None = None,
        on_tool_status: Callable[[str, str, str | None], Awaitable[None] | None] | None = None,
    ) -> None:
        self.repo = repo
        self.llm = llm
        self.emotion = emotion
        self.tools = tools
        self.on_emotion = on_emotion
        self.on_tool_status = on_tool_status
        self._wired_emotion = False
        self._busy = False
        self._wire_emotion()

    @property
    def is_busy(self) -> bool:
        return self._busy

    def _wire_emotion(self) -> None:
        if self._wired_emotion:
            return

        def _cb(state: Emotion) -> None:
            self.repo.set_pet_state("emotion", state.value)
            if self.on_emotion:
                result = self.on_emotion(state)
                if hasattr(result, "__await__"):
                    pass

        self.emotion.set_on_change(_cb)
        saved = self.repo.get_pet_state("emotion")
        if saved:
            try:
                self.emotion.state = Emotion(saved)
            except ValueError:
                pass
        self._wired_emotion = True

    async def _emit_emotion(self, state: Emotion) -> None:
        if self.on_emotion:
            result = self.on_emotion(state)
            if hasattr(result, "__await__"):
                await result

    async def _emit_tool(self, name: str, status: str, detail: str | None = None) -> None:
        if self.on_tool_status:
            result = self.on_tool_status(name, status, detail)
            if hasattr(result, "__await__"):
                await result

    def _build_messages(self, session_id: str, user_text: str) -> list[dict[str, Any]]:
        recent = self.repo.list_messages(session_id, limit=40)
        summary = self.repo.get_pet_state(f"summary:{session_id}")
        file_block = format_file_memory_block() or None
        hits = search_memory(self.repo.conn, user_text, limit=5)
        fts_block = format_memory_block(hits) or None
        now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        persona = SYSTEM_PERSONA + f"\n当前本地时间：{now}。"
        return build_context_messages(
            persona=persona,
            emotion_prompt=self.emotion.prompt_fragment(),
            summary=summary,
            file_memory_block=file_block,
            memory_block=fts_block,
            recent=recent,
        )

    def _remember_exchange(self, user_text: str, assistant_text: str) -> None:
        # Prefer preference-like user lines and short assistant facts
        if any(k in user_text for k in ("我喜欢", "我是", "叫我", "记住", "偏好", "不要")):
            add_memory(self.repo.conn, f"用户：{user_text}", kind="preference")
        snippet = assistant_text.strip()
        if len(snippet) > 8:
            add_memory(
                self.repo.conn,
                f"用户问：{user_text[:80]} / 猫说：{snippet[:160]}",
                kind="dialogue",
            )

    async def handle_user_message(
        self, text: str, session_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        self._busy = True
        try:
            async for event in self._handle_user_message_inner(text, session_id):
                yield event
        finally:
            self._busy = False

    async def _handle_user_message_inner(
        self, text: str, session_id: str | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        sid = self.repo.ensure_session(session_id)
        state = self.emotion.on_user_message()
        yield {"type": "emotion_changed", "payload": {"state": state.value}}
        await self._emit_emotion(state)

        self.repo.add_message(sid, "user", text)
        # Opportunistic summarization (best-effort, non-fatal)
        try:
            await maybe_summarize_session(self.repo, self.llm, sid)
        except Exception:  # noqa: BLE001
            pass

        messages = self._build_messages(sid, text)
        tool_defs = self.tools.openai_tools() if self.tools.has_tools() else None

        try:
            for _ in range(5):
                result = await self.llm.chat(messages, tools=tool_defs)
                if result.tool_calls:
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": result.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": tc.arguments,
                                },
                            }
                            for tc in result.tool_calls
                        ],
                    }
                    messages.append(assistant_msg)
                    for tc in result.tool_calls:
                        logger.info(
                            "llm tool_call name=%s arguments=%s",
                            tc.name,
                            tc.arguments,
                        )
                        yield {
                            "type": "tool_status",
                            "payload": {
                                "name": tc.name,
                                "status": "running",
                                "detail": None,
                            },
                        }
                        await self._emit_tool(tc.name, "running", None)
                        try:
                            out = await self.tools.execute(tc.name, tc.arguments)
                            detail = (
                                json.dumps(out, ensure_ascii=False)
                                if not isinstance(out, str)
                                else out
                            )
                            status = "done"
                            logger.info("llm tool_result name=%s detail=%s", tc.name, detail)
                        except Exception as exc:  # noqa: BLE001
                            detail = str(exc)
                            status = "error"
                            out = {"error": detail}
                            logger.exception("llm tool_error name=%s", tc.name)
                        yield {
                            "type": "tool_status",
                            "payload": {
                                "name": tc.name,
                                "status": status,
                                "detail": detail,
                            },
                        }
                        await self._emit_tool(tc.name, status, detail)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": detail
                                if isinstance(detail, str)
                                else json.dumps(out, ensure_ascii=False),
                            }
                        )
                    continue

                first = True
                if result.content:
                    text_out = result.content
                    cleaned, tagged = EmotionStateMachine.parse_emotion_tag(text_out)
                    if first:
                        speak = self.emotion.on_first_token()
                        yield {"type": "emotion_changed", "payload": {"state": speak.value}}
                        await self._emit_emotion(speak)
                        first = False
                    chunk_size = 8
                    for i in range(0, len(cleaned), chunk_size):
                        piece = cleaned[i : i + chunk_size]
                        yield {
                            "type": "token",
                            "payload": {"text": piece, "session_id": sid},
                        }
                    if tagged:
                        emo = self.emotion.apply_labeled_emotion(tagged)
                    else:
                        emo = self.emotion.infer_from_text(cleaned)
                    yield {"type": "emotion_changed", "payload": {"state": emo.value}}
                    await self._emit_emotion(emo)
                    self.repo.add_message(sid, "assistant", cleaned)
                    self._remember_exchange(text, cleaned)
                    yield {"type": "done", "payload": {"session_id": sid, "text": cleaned}}
                    return

                stream_buf: list[str] = []
                async for delta in self.llm.chat_stream(messages, tools=None):
                    if first:
                        speak = self.emotion.on_first_token()
                        yield {"type": "emotion_changed", "payload": {"state": speak.value}}
                        await self._emit_emotion(speak)
                        first = False
                    stream_buf.append(delta)
                    yield {"type": "token", "payload": {"text": delta, "session_id": sid}}
                raw = "".join(stream_buf)
                cleaned, tagged = EmotionStateMachine.parse_emotion_tag(raw)
                if tagged:
                    emo = self.emotion.apply_labeled_emotion(tagged)
                else:
                    emo = self.emotion.infer_from_text(cleaned or "")
                yield {"type": "emotion_changed", "payload": {"state": emo.value}}
                await self._emit_emotion(emo)
                self.repo.add_message(sid, "assistant", cleaned)
                self._remember_exchange(text, cleaned)
                yield {"type": "done", "payload": {"session_id": sid, "text": cleaned}}
                return

            yield {
                "type": "error",
                "payload": {"message": "工具调用轮次过多", "code": "tool_loop"},
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("llm chat failed: %s", exc)
            sad = self.emotion.on_error()
            yield {"type": "emotion_changed", "payload": {"state": sad.value}}
            await self._emit_emotion(sad)
            yield {"type": "error", "payload": {"message": str(exc), "code": "llm_error"}}
