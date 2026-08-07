"""Tests for dynamic LLM model profile list."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.llm.openai_compatible import LLMSettings


def test_model_profile_crud_and_activate():
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(db_file=str(Path(tmp) / "t.db"))
        client = TestClient(app)

        with patch("backend.core.config_service.set_api_key"), patch(
            "backend.core.config_service.get_api_key", return_value="sk-a"
        ), patch(
            "backend.app.load_llm_settings",
            return_value=LLMSettings(
                provider_preset="deepseek",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                api_key="sk-a",
            ),
        ):
            listed = client.get("/config").json()
            assert isinstance(listed["profiles"], list)
            assert listed["active_profile"]
            assert any(p["id"] == "deepseek" for p in listed["profiles"])

            created = client.post(
                "/config/profiles",
                json={
                    "name": "公司网关",
                    "base_url": "https://example.com/v1",
                    "model": "my-model",
                    "api_key": "sk-b",
                    "activate": False,
                },
            )
            assert created.status_code == 200
            body = created.json()
            assert body["active_profile"] == "deepseek"
            new_id = next(p["id"] for p in body["profiles"] if p["name"] == "公司网关")
            assert any(p["model"] == "my-model" for p in body["profiles"])

            activated = client.put("/config/active", json={"active_profile": new_id})
            assert activated.status_code == 200
            assert activated.json()["active_profile"] == new_id
            assert activated.json()["model"] == "my-model"

            updated = client.put(
                f"/config/profiles/{new_id}",
                json={"model": "my-model-v2", "activate": True},
            )
            assert updated.status_code == 200
            assert updated.json()["model"] == "my-model-v2"

            deleted = client.delete(f"/config/profiles/{new_id}")
            assert deleted.status_code == 200
            assert not any(p["id"] == new_id for p in deleted.json()["profiles"])
            assert deleted.json()["active_profile"] != new_id
