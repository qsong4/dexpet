"""LLM client unit tests with mocked AsyncOpenAI."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.llm.openai_compatible import LLMSettings, OpenAICompatibleClient


@pytest.mark.asyncio
async def test_chat_passes_base_url_model_and_messages():
    mock_client = MagicMock()
    mock_message = SimpleNamespace(content="hello", tool_calls=None)
    mock_choice = SimpleNamespace(message=mock_message, finish_reason="stop")
    mock_resp = SimpleNamespace(choices=[mock_choice])
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    settings = LLMSettings(
        provider_preset="custom",
        base_url="https://example.com/v1",
        model="my-model",
        api_key="sk-test",
    )
    llm = OpenAICompatibleClient(settings, client=mock_client)
    result = await llm.chat([{"role": "user", "content": "hi"}])
    assert result.content == "hello"
    kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert kwargs["model"] == "my-model"
    assert kwargs["messages"][0]["content"] == "hi"


@pytest.mark.asyncio
async def test_chat_parses_tool_calls():
    mock_client = MagicMock()
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="create_reminder", arguments='{"message":"x","fire_at":"t"}'),
    )
    mock_message = SimpleNamespace(content=None, tool_calls=[tc])
    mock_choice = SimpleNamespace(message=mock_message, finish_reason="tool_calls")
    mock_resp = SimpleNamespace(choices=[mock_choice])
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    settings = LLMSettings(api_key="sk-test", base_url="https://api.deepseek.com", model="deepseek-chat")
    llm = OpenAICompatibleClient(settings, client=mock_client)
    result = await llm.chat([{"role": "user", "content": "提醒我"}])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "create_reminder"


def test_requires_api_key():
    with pytest.raises(ValueError):
        OpenAICompatibleClient(LLMSettings(api_key=""))


def test_timeout_config_uses_settings():
    settings = LLMSettings(
        api_key="sk-test",
        connect_timeout=12.0,
        read_timeout=90.0,
    )
    timeout = OpenAICompatibleClient._timeout_config(settings)
    assert timeout.connect == 12.0
    assert timeout.read == 90.0


def test_format_api_error_timeout_is_actionable():
    settings = LLMSettings(
        api_key="sk-test",
        base_url="http://10.140.0.200:5693/v1",
        model="CheryFS-Deepseek-V4",
    )
    llm = OpenAICompatibleClient(settings, client=MagicMock())
    msg = llm._format_api_error(TimeoutError("Request timed out."))
    assert "连接超时/不可达" in msg
    assert "http://10.140.0.200:5693/v1/chat/completions" in msg
    assert "切换到其他可用模型" in msg


@pytest.mark.asyncio
async def test_chat_timeout_surfaces_runtime_error():
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=TimeoutError("Request timed out."))
    settings = LLMSettings(
        api_key="sk-test",
        base_url="http://10.0.0.1:1/v1",
        model="slow-model",
    )
    llm = OpenAICompatibleClient(settings, client=mock_client)
    with pytest.raises(RuntimeError, match="连接超时/不可达"):
        await llm.chat([{"role": "user", "content": "hi"}])
