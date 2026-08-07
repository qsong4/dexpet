"""Session history truncation and summarization."""

from __future__ import annotations

from typing import Any

from backend.core.llm.openai_compatible import OpenAICompatibleClient
from backend.db.repository import Repository

# Keep recent turns; summarize older ones into pet_state.
RECENT_MESSAGE_LIMIT = 16
SUMMARIZE_TRIGGER = 28


async def maybe_summarize_session(
    repo: Repository,
    llm: OpenAICompatibleClient,
    session_id: str,
) -> str | None:
    """If history is long, compress older messages into a running summary.

    Returns updated summary text when summarization ran, else None.
    """
    history = repo.list_messages(session_id, limit=200)
    if len(history) < SUMMARIZE_TRIGGER:
        return None

    older = history[:-RECENT_MESSAGE_LIMIT]
    if not older:
        return None

    prev = repo.get_pet_state(f"summary:{session_id}", "") or ""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in older[-40:])
    prompt = [
        {
            "role": "system",
            "content": (
                "你是会话摘要助手。请把对话压缩成简洁中文要点（偏好、事实、待办），"
                "不超过 180 字。不要情绪标签。"
            ),
        },
        {
            "role": "user",
            "content": f"已有摘要：\n{prev or '（无）'}\n\n新增对话：\n{transcript}",
        },
    ]
    result = await llm.chat(prompt, tools=None, temperature=0.2)
    summary = (result.content or "").strip()
    if not summary:
        return None
    repo.set_pet_state(f"summary:{session_id}", summary)
    return summary


def build_context_messages(
    *,
    persona: str,
    emotion_prompt: str,
    summary: str | None,
    memory_block: str | None,
    recent: list[dict[str, Any]],
    file_memory_block: str | None = None,
) -> list[dict[str, Any]]:
    system_parts = [persona, emotion_prompt]
    if file_memory_block:
        system_parts.append(file_memory_block)
    if summary:
        system_parts.append(f"会话摘要：\n{summary}")
    if memory_block:
        system_parts.append(memory_block)
    messages: list[dict[str, Any]] = [{"role": "system", "content": "\n\n".join(system_parts)}]
    for row in recent[-RECENT_MESSAGE_LIMIT:]:
        messages.append({"role": row["role"], "content": row["content"]})
    return messages
