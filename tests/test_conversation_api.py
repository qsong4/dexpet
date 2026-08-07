"""Conversation + HTTP/WS integration with mocked LLM."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.conversation import ConversationManager
from backend.core.emotion import EmotionStateMachine
from backend.core.llm.openai_compatible import OpenAICompatibleClient, LLMSettings
from backend.core.tools import ToolRouter
from backend.db.repository import Repository
from backend.db.schema import connect, init_db


@pytest.mark.asyncio
async def test_conversation_streams_tokens_and_emotion():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        mock_client = MagicMock()
        mock_message = SimpleNamespace(
            content="你好呀 [[emotion:happy]]",
            tool_calls=None,
        )
        mock_choice = SimpleNamespace(message=mock_message, finish_reason="stop")
        mock_resp = SimpleNamespace(choices=[mock_choice])
        mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
        llm = OpenAICompatibleClient(
            LLMSettings(api_key="sk", base_url="https://example.com/v1", model="m"),
            client=mock_client,
        )
        tools = ToolRouter()
        mgr = ConversationManager(repo, llm, EmotionStateMachine(), tools)
        events = []
        async for ev in mgr.handle_user_message("hi"):
            events.append(ev)
        types = [e["type"] for e in events]
        assert "emotion_changed" in types
        assert "token" in types
        assert "done" in types
        assert any(
            e["type"] == "emotion_changed" and e["payload"]["state"] == "happy"
            for e in events
        )
        conn.close()


def test_health_and_config_endpoints():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        client = TestClient(app)
        assert client.get("/health").json()["status"] == "ok"
        cfg = client.get("/config").json()
        assert cfg["model"] == "deepseek-chat"
        with (
            patch("backend.core.config_service.set_api_key") as mock_set,
            patch("backend.core.config_service.get_api_key", return_value="sk-test-key"),
            patch("backend.app.load_llm_settings") as mock_load,
        ):
            mock_load.return_value = LLMSettings(
                provider_preset="custom",
                base_url="https://api.example.com",
                model="foo-model",
                api_key="sk-test-key",
            )
            resp = client.put(
                "/config",
                json={
                    "provider_preset": "custom",
                    "base_url": "https://api.example.com",
                    "model": "foo-model",
                    "api_key": "sk-test-key",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["model"] == "foo-model"
            assert body["base_url"] == "https://api.example.com"
            assert body["api_key_set"] is True
            assert body["active_profile"] == "custom"
            mock_set.assert_called_once_with("sk-test-key", "custom")
