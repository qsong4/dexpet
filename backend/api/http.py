"""FastAPI HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from backend.api.settings_page import SETTINGS_HTML
from backend.core.app_whitelist import (
    entries_to_mapping,
    get_app_whitelist,
    reset_app_whitelist,
    save_app_whitelist,
    whitelist_as_entries,
)
from backend.core.config_service import (
    create_profile,
    delete_profile,
    public_llm_config,
    save_llm_config,
    set_active_profile,
    update_profile,
)
from backend.core.memory import search_memory
from backend.core.memory_config import load_memory_config, save_memory_config
from backend.core.memory_files import (
    clear_memory_files,
    memory_dir,
    profile_mtime,
    profile_path,
    read_meta,
    read_profile,
    write_profile,
)
from backend.core.pet_display import load_pet_display, save_pet_display
from backend.core.sprites import delete_sprite, find_sprite_file, list_sprites, save_sprite
from backend.paths import DEFAULT_HOST, DEFAULT_PORT
from shared.messages import (
    ActiveProfileUpdate,
    AppWhitelistUpdate,
    LLMConfigUpdate,
    MemoryConfigUpdate,
    MemoryProfileUpdate,
    MessageType,
    ModelProfileCreate,
    ModelProfileUpdate,
    PetSettingsUpdate,
)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/settings", response_class=HTMLResponse)
async def settings_page() -> str:
    return SETTINGS_HTML


@router.get("/config")
async def get_config(request: Request):
    repo = request.app.state.repo
    return public_llm_config(repo).model_dump()


@router.put("/config")
async def put_config(request: Request, body: LLMConfigUpdate):
    repo = request.app.state.repo
    result = save_llm_config(repo, body)
    from backend.app import rebuild_llm

    rebuild_llm(request.app)
    return result.model_dump()


@router.put("/config/active")
async def put_active_profile(request: Request, body: ActiveProfileUpdate):
    repo = request.app.state.repo
    try:
        result = set_active_profile(repo, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from backend.app import rebuild_llm

    rebuild_llm(request.app)
    return result.model_dump()


@router.post("/config/profiles")
async def post_profile(request: Request, body: ModelProfileCreate):
    repo = request.app.state.repo
    result = create_profile(repo, body)
    from backend.app import rebuild_llm

    rebuild_llm(request.app)
    return result.model_dump()


@router.put("/config/profiles/{profile_id}")
async def put_profile(request: Request, profile_id: str, body: ModelProfileUpdate):
    repo = request.app.state.repo
    try:
        result = update_profile(repo, profile_id, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    from backend.app import rebuild_llm

    rebuild_llm(request.app)
    return result.model_dump()


@router.delete("/config/profiles/{profile_id}")
async def remove_profile(request: Request, profile_id: str):
    repo = request.app.state.repo
    try:
        result = delete_profile(repo, profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    from backend.app import rebuild_llm

    rebuild_llm(request.app)
    return result.model_dump()


@router.get("/history")
async def history(request: Request, session_id: str, limit: int = 50):
    repo = request.app.state.repo
    return {"messages": repo.list_messages(session_id, limit=limit)}


@router.get("/memory")
async def memory_search(request: Request, q: str = "", limit: int = 10):
    hits = search_memory(request.app.state.repo.conn, q, limit=limit)
    return {"hits": hits}


@router.get("/config/memory")
async def get_memory_config(request: Request):
    cfg = load_memory_config(request.app.state.repo)
    meta = read_meta()
    return {
        "config": cfg,
        "memory_dir": str(memory_dir()),
        "profile_preview": read_profile()[:4000],
        "profile_mtime": profile_mtime(),
        "digest_failure": meta.get("last_digest_failure"),
    }


@router.put("/config/memory")
async def put_memory_config(request: Request, body: MemoryConfigUpdate):
    updates = body.model_dump(exclude_none=True)
    cfg = save_memory_config(request.app.state.repo, updates)
    sched = getattr(request.app.state, "memory_scheduler", None)
    if sched is not None:
        try:
            sched.ensure_jobs()
        except Exception:  # noqa: BLE001
            pass
    return {"config": cfg, "memory_dir": str(memory_dir())}


@router.get("/memory/profile")
async def get_memory_profile():
    """Full profile.md for settings editor."""
    content = read_profile()
    return {
        "content": content,
        "mtime": profile_mtime(),
        "path": str(profile_path()),
    }


@router.put("/memory/profile")
async def put_memory_profile(body: MemoryProfileUpdate):
    """
    Save profile.md.

    Concurrency: optimistic via if_mtime. If file changed since load and force=false,
    return 409 with current content. force=true = last-write-wins overwrite.
    Nightly digest also overwrites profile (last-write-wins); UI warns on save.
    """
    current_mtime = profile_mtime()
    if (
        body.if_mtime is not None
        and not body.force
        and current_mtime > 0
        and abs(current_mtime - float(body.if_mtime)) > 1e-6
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "conflict": True,
                "message": "画像已在别处被修改（可能是夜间整理）。确认覆盖或重新加载。",
                "content": read_profile(),
                "mtime": current_mtime,
            },
        )
    text = body.content if body.content.endswith("\n") or body.content == "" else body.content + "\n"
    write_profile(text)
    return {
        "ok": True,
        "content": read_profile(),
        "mtime": profile_mtime(),
        "path": str(profile_path()),
    }


@router.post("/memory/clear")
async def clear_memory(request: Request):
    clear_memory_files(include_meta=True)
    # Best-effort: also wipe FTS profile/daily kinds (keep preference/dialogue)
    conn = request.app.state.repo.conn
    try:
        conn.execute("DELETE FROM memory_fts WHERE kind IN ('profile', 'daily')")
        conn.commit()
    except Exception:  # noqa: BLE001
        pass
    sched = getattr(request.app.state, "memory_scheduler", None)
    if sched is not None:
        try:
            sched.ensure_jobs()
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "memory_dir": str(memory_dir())}


@router.post("/memory/digest")
async def run_memory_digest(request: Request, force: bool = True):
    digest = getattr(request.app.state, "memory_digest", None)
    if digest is None:
        raise HTTPException(status_code=503, detail="memory digest unavailable")
    from datetime import date

    try:
        result = await digest.run(for_date=date.today(), force=force)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/memory/check")
async def run_memory_check(request: Request):
    proactive = getattr(request.app.state, "memory_proactive", None)
    if proactive is None:
        raise HTTPException(status_code=503, detail="memory proactive unavailable")
    try:
        result = await proactive.check_once()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/memory/open-dir")
async def open_memory_dir():
    import subprocess

    path = memory_dir()
    try:
        subprocess.Popen(["open", str(path)])  # noqa: S603,S607
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "memory_dir": str(path)}


@router.get("/sprites")
async def get_sprites():
    return {"sprites": list_sprites()}


@router.get("/sprites/{emotion}/image")
async def get_sprite_image(emotion: str):
    try:
        path = find_sprite_file(emotion)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path is None:
        raise HTTPException(status_code=404, detail="未设置该情绪形象")
    return FileResponse(path)


@router.post("/sprites/{emotion}")
async def upload_sprite(emotion: str, file: UploadFile = File(...)):
    try:
        data = await file.read()
        path = save_sprite(emotion, data, file.filename or "sprite.png")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "emotion": emotion, "filename": path.name, "sprites": list_sprites()}


@router.delete("/sprites/{emotion}")
async def remove_sprite(emotion: str):
    try:
        deleted = delete_sprite(emotion)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "deleted": deleted, "sprites": list_sprites()}


@router.get("/pet")
async def get_pet_settings(request: Request):
    repo = request.app.state.repo
    return load_pet_display(repo)


@router.put("/pet")
async def put_pet_settings(request: Request, body: PetSettingsUpdate):
    repo = request.app.state.repo
    hub = getattr(request.app.state, "ws_hub", None)
    system = getattr(request.app.state, "system", None)
    result: dict = {}
    broadcast_payload: dict = {}
    if body.always_on_top is not None:
        if system is not None:
            result = system.set_always_on_top(body.always_on_top)
        else:
            repo.set_pet_state("always_on_top", "1" if body.always_on_top else "0")
            result = {"ok": True, "always_on_top": body.always_on_top}
        broadcast_payload["always_on_top"] = body.always_on_top
    if body.renderer is not None or body.live2d_model_path is not None:
        display = save_pet_display(
            repo,
            renderer=body.renderer,
            live2d_model_path=body.live2d_model_path,
        )
        result.update(display)
        if body.renderer is not None:
            broadcast_payload["renderer"] = display["renderer"]
        if body.live2d_model_path is not None:
            broadcast_payload["live2d_model_path"] = display["live2d_model_path"]
        broadcast_payload["effective_renderer"] = display["effective_renderer"]
        broadcast_payload["live2d_error"] = display.get("live2d_error")
        broadcast_payload["live2d_available"] = display.get("live2d_available")
    display_changed = body.renderer is not None or body.live2d_model_path is not None
    # system.set_always_on_top already broadcasts when the plugin is wired
    need_broadcast = display_changed or (
        body.always_on_top is not None and system is None
    )
    if hub is not None and need_broadcast and broadcast_payload:
        hub.schedule_broadcast(
            {
                "type": MessageType.PET_SETTINGS.value,
                "payload": broadcast_payload,
            }
        )
    return {**load_pet_display(repo), **result}


@router.get("/system/app-whitelist")
async def get_app_whitelist_api(request: Request):
    repo = request.app.state.repo
    mapping = get_app_whitelist(repo)
    return {"entries": whitelist_as_entries(mapping)}


@router.put("/system/app-whitelist")
async def put_app_whitelist_api(request: Request, body: AppWhitelistUpdate):
    repo = request.app.state.repo
    mapping = entries_to_mapping([e.model_dump() for e in body.entries])
    if not mapping:
        raise HTTPException(status_code=400, detail="白名单不能为空")
    saved = save_app_whitelist(repo, mapping)
    return {"ok": True, "entries": whitelist_as_entries(saved)}


@router.post("/system/app-whitelist/reset")
async def reset_app_whitelist_api(request: Request):
    repo = request.app.state.repo
    saved = reset_app_whitelist(repo)
    return {"ok": True, "entries": whitelist_as_entries(saved)}


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "app": "DexPet",
        "settings": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/settings",
        "health": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/health",
    }
