"""LLM model profiles: dynamic list + active switch."""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend.core.llm.openai_compatible import LLMSettings
from backend.core.secrets import delete_api_key, get_api_key, set_api_key
from backend.db.repository import Repository
from backend.paths import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from shared.messages import (
    ActiveProfileUpdate,
    LLMConfigPublic,
    ModelProfileCreate,
    ModelProfilePublic,
    ModelProfileUpdate,
)

PROFILES_KEY = "llm_profiles_v2"
PROFILES_V2_FLAG = "profiles_v2_migrated"

DEFAULT_SEED: list[dict[str, str]] = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL,
    },
]


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _legacy_profile_dict(repo: Repository, name: str) -> dict[str, str]:
    defaults = {
        "deepseek": {"base_url": DEEPSEEK_BASE_URL, "model": DEEPSEEK_MODEL},
        "custom": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    }
    raw = repo.get_setting(f"profile:{name}")
    base = defaults.get(name, defaults["deepseek"])
    if not raw:
        return dict(base)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(base)
    return {
        "base_url": data.get("base_url") or base["base_url"],
        "model": data.get("model") or base["model"],
    }


def _migrate_to_v2(repo: Repository) -> None:
    if repo.get_setting(PROFILES_V2_FLAG) == "1":
        return

    # Ensure old dual-profile migration ran first (if any legacy flat keys)
    if repo.get_setting("profiles_migrated") != "1":
        legacy_preset = repo.get_setting("provider_preset", "deepseek") or "deepseek"
        legacy_base = repo.get_setting("base_url")
        legacy_model = repo.get_setting("model")
        if legacy_base or legacy_model:
            data = {
                "base_url": legacy_base or DEEPSEEK_BASE_URL,
                "model": legacy_model or DEEPSEEK_MODEL,
            }
            repo.set_setting(f"profile:{legacy_preset}", json.dumps(data))
            other = "custom" if legacy_preset == "deepseek" else "deepseek"
            if repo.get_setting(f"profile:{other}") is None:
                other_def = (
                    {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}
                    if other == "custom"
                    else {"base_url": DEEPSEEK_BASE_URL, "model": DEEPSEEK_MODEL}
                )
                repo.set_setting(f"profile:{other}", json.dumps(other_def))
            repo.set_setting("active_profile", legacy_preset)
            legacy_key = get_api_key(None)
            if legacy_key:
                set_api_key(legacy_key, legacy_preset)
        else:
            repo.set_setting(
                "profile:deepseek",
                json.dumps({"base_url": DEEPSEEK_BASE_URL, "model": DEEPSEEK_MODEL}),
            )
            repo.set_setting(
                "profile:custom",
                json.dumps({"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}),
            )
            repo.set_setting("active_profile", "deepseek")
        repo.set_setting("profiles_migrated", "1")

    # Convert dual slots → list (keep ids so Keychain keys still match)
    deepseek = _legacy_profile_dict(repo, "deepseek")
    custom = _legacy_profile_dict(repo, "custom")
    profiles = [
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "base_url": deepseek["base_url"],
            "model": deepseek["model"],
        },
        {
            "id": "custom",
            "name": "自定义",
            "base_url": custom["base_url"],
            "model": custom["model"],
        },
    ]
    # Drop custom if it still looks unused and deepseek is enough? Keep both for compat.
    repo.set_setting_json(PROFILES_KEY, profiles)
    active = repo.get_setting("active_profile") or "deepseek"
    if active not in {"deepseek", "custom"}:
        active = "deepseek"
    repo.set_setting("active_profile", active)
    repo.set_setting(PROFILES_V2_FLAG, "1")


def _load_raw_profiles(repo: Repository) -> list[dict[str, Any]]:
    _migrate_to_v2(repo)
    raw = repo.get_setting_json(PROFILES_KEY, None)
    if not isinstance(raw, list) or not raw:
        repo.set_setting_json(PROFILES_KEY, DEFAULT_SEED)
        return [dict(p) for p in DEFAULT_SEED]
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip() or _new_id()
        name = str(item.get("name") or "未命名").strip() or "未命名"
        base_url = str(item.get("base_url") or "").strip() or DEEPSEEK_BASE_URL
        model = str(item.get("model") or "").strip() or DEEPSEEK_MODEL
        out.append({"id": pid, "name": name, "base_url": base_url, "model": model})
    if not out:
        out = [dict(p) for p in DEFAULT_SEED]
        repo.set_setting_json(PROFILES_KEY, out)
    return out


def _save_raw_profiles(repo: Repository, profiles: list[dict[str, Any]]) -> None:
    repo.set_setting_json(PROFILES_KEY, profiles)


def _to_public(repo: Repository, item: dict[str, Any]) -> ModelProfilePublic:
    pid = str(item["id"])
    return ModelProfilePublic(
        id=pid,
        name=str(item["name"]),
        base_url=str(item["base_url"]),
        model=str(item["model"]),
        api_key_set=bool(get_api_key(pid)),
    )


def get_active_profile_id(repo: Repository) -> str:
    profiles = _load_raw_profiles(repo)
    ids = {p["id"] for p in profiles}
    active = repo.get_setting("active_profile") or profiles[0]["id"]
    if active not in ids:
        active = profiles[0]["id"]
        repo.set_setting("active_profile", active)
    return active


def public_llm_config(repo: Repository) -> LLMConfigPublic:
    profiles = _load_raw_profiles(repo)
    active = get_active_profile_id(repo)
    public_list = [_to_public(repo, p) for p in profiles]
    current = next(p for p in public_list if p.id == active)
    return LLMConfigPublic(
        active_profile=active,
        provider_preset=active,
        base_url=current.base_url,
        model=current.model,
        api_key_set=current.api_key_set,
        profiles=public_list,
    )


def load_llm_settings(repo: Repository) -> LLMSettings:
    cfg = public_llm_config(repo)
    api_key = get_api_key(cfg.active_profile) or get_api_key(None) or ""
    return LLMSettings(
        provider_preset=cfg.active_profile,
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=api_key,
    )


def create_profile(repo: Repository, body: ModelProfileCreate) -> LLMConfigPublic:
    profiles = _load_raw_profiles(repo)
    pid = _new_id()
    profiles.append(
        {
            "id": pid,
            "name": body.name.strip() or "新模型",
            "base_url": body.base_url.strip(),
            "model": body.model.strip(),
        }
    )
    _save_raw_profiles(repo, profiles)
    if body.api_key:
        set_api_key(body.api_key, pid)
    if body.activate:
        repo.set_setting("active_profile", pid)
        repo.set_setting("provider_preset", pid)
    return public_llm_config(repo)


def update_profile(repo: Repository, profile_id: str, body: ModelProfileUpdate) -> LLMConfigPublic:
    profiles = _load_raw_profiles(repo)
    found = None
    for item in profiles:
        if item["id"] == profile_id:
            found = item
            break
    if found is None:
        raise KeyError(f"模型不存在：{profile_id}")
    if body.name is not None:
        found["name"] = body.name.strip() or found["name"]
    if body.base_url is not None:
        found["base_url"] = body.base_url.strip() or found["base_url"]
    if body.model is not None:
        found["model"] = body.model.strip() or found["model"]
    _save_raw_profiles(repo, profiles)
    if body.api_key:
        set_api_key(body.api_key, profile_id)
    if body.activate:
        repo.set_setting("active_profile", profile_id)
        repo.set_setting("provider_preset", profile_id)
    return public_llm_config(repo)


def delete_profile(repo: Repository, profile_id: str) -> LLMConfigPublic:
    profiles = _load_raw_profiles(repo)
    if len(profiles) <= 1:
        raise ValueError("至少保留一个模型配置")
    if not any(p["id"] == profile_id for p in profiles):
        raise KeyError(f"模型不存在：{profile_id}")
    profiles = [p for p in profiles if p["id"] != profile_id]
    _save_raw_profiles(repo, profiles)
    delete_api_key(profile_id)
    active = repo.get_setting("active_profile")
    if active == profile_id:
        repo.set_setting("active_profile", profiles[0]["id"])
        repo.set_setting("provider_preset", profiles[0]["id"])
    return public_llm_config(repo)


def set_active_profile(repo: Repository, update: ActiveProfileUpdate) -> LLMConfigPublic:
    profiles = _load_raw_profiles(repo)
    ids = {p["id"] for p in profiles}
    if update.active_profile not in ids:
        raise KeyError(f"模型不存在：{update.active_profile}")
    repo.set_setting("active_profile", update.active_profile)
    repo.set_setting("provider_preset", update.active_profile)
    return public_llm_config(repo)


def save_llm_config(repo: Repository, update: Any) -> LLMConfigPublic:
    """Legacy PUT /config: update existing id or create if missing."""
    from shared.messages import LLMConfigUpdate, ModelProfileCreate, ModelProfileUpdate

    if not isinstance(update, LLMConfigUpdate):
        update = LLMConfigUpdate.model_validate(update)
    profiles = _load_raw_profiles(repo)
    ids = {p["id"] for p in profiles}
    pid = update.provider_preset
    if pid in ids:
        return update_profile(
            repo,
            pid,
            ModelProfileUpdate(
                name=update.name,
                base_url=update.base_url,
                model=update.model,
                api_key=update.api_key,
                activate=update.activate,
            ),
        )
    return create_profile(
        repo,
        ModelProfileCreate(
            name=update.name or pid,
            base_url=update.base_url,
            model=update.model,
            api_key=update.api_key,
            activate=update.activate,
        ),
    )
