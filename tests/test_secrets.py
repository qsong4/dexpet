"""API key storage: keyring with file fallback when Keychain is unavailable."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import keyring.errors

from backend.core import secrets


def test_set_api_key_falls_back_to_file_when_keyring_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "data_dir", lambda: tmp_path)

    def boom(*_a, **_k):
        raise keyring.errors.PasswordSetError("Can't store password on keychain")

    with (
        patch.object(secrets.keyring, "set_password", side_effect=boom),
        patch.object(secrets.keyring, "get_password", return_value=None),
    ):
        secrets.set_api_key("sk-fallback", "custom")
        store = tmp_path / "secrets" / "api_keys.json"
        assert store.is_file()
        assert secrets.get_api_key("custom") == "sk-fallback"
        assert secrets.get_api_key(None) == "sk-fallback"


def test_get_api_key_prefers_keyring_over_file(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "data_dir", lambda: tmp_path)
    secrets._set_file_key("llm_api_key_custom", "from-file")

    with patch.object(secrets.keyring, "get_password", return_value="from-keyring"):
        assert secrets.get_api_key("custom") == "from-keyring"


def test_delete_api_key_clears_file_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(secrets, "data_dir", lambda: tmp_path)
    secrets._set_file_key("llm_api_key_custom", "sk-x")

    with (
        patch.object(
            secrets.keyring,
            "delete_password",
            side_effect=keyring.errors.PasswordDeleteError(),
        ),
        patch.object(secrets.keyring, "get_password", return_value=None),
    ):
        secrets.delete_api_key("custom")
        assert secrets.get_api_key("custom") is None


def test_put_profile_succeeds_when_keyring_rejects(tmp_path, monkeypatch):
    """Regression: settings「保存模型」must not 500 when Keychain write fails."""
    from fastapi.testclient import TestClient

    from backend.app import create_app
    from backend.core.llm.openai_compatible import LLMSettings

    monkeypatch.setattr(secrets, "data_dir", lambda: tmp_path)

    def boom(*_a, **_k):
        raise keyring.errors.PasswordSetError(
            "Can't store password on keychain: (100001, 'Unknown Error')"
        )

    app = create_app(db_file=str(Path(tmp_path) / "t.db"))
    client = TestClient(app)

    with (
        patch("backend.core.secrets.keyring.set_password", side_effect=boom),
        patch("backend.core.secrets.keyring.get_password", return_value=None),
        patch(
            "backend.app.load_llm_settings",
            return_value=LLMSettings(
                provider_preset="custom",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
                api_key="sk-new",
            ),
        ),
    ):
        resp = client.put(
            "/config/profiles/custom",
            json={
                "name": "custom",
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-chat",
                "api_key": "sk-new",
            },
        )
        assert resp.status_code == 200, resp.text
        custom = next(p for p in resp.json()["profiles"] if p["id"] == "custom")
        assert custom["api_key_set"] is True
        assert secrets.get_api_key("custom") == "sk-new"
