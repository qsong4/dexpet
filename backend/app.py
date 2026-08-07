"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from backend.api.http import router as http_router
from backend.api.hub import WsHub
from backend.api.ws import router as ws_router
from backend.core.config_service import load_llm_settings
from backend.core.conversation import ConversationManager
from backend.core.emotion import EmotionStateMachine
from backend.core.llm.openai_compatible import OpenAICompatibleClient
from backend.core.memory_digest import MemoryDigestService
from backend.core.memory_proactive import MemoryProactiveService
from backend.core.memory_scheduler import MemoryScheduler
from backend.core.tools import ToolRouter
from backend.db.repository import Repository
from backend.db.schema import connect, init_db
from backend.paths import db_path
from backend.plugins.reminder import ReminderPlugin
from backend.plugins.stock import StockPlugin
from backend.plugins.system_control import SystemControlPlugin
from shared.messages import MessageType


def rebuild_llm(app: FastAPI) -> None:
    repo: Repository = app.state.repo
    settings = load_llm_settings(repo)
    if not settings.api_key:
        app.state.llm = None
        app.state.conversation = None
        if getattr(app.state, "memory_digest", None) is not None:
            app.state.memory_digest.set_llm(None)
        if getattr(app.state, "memory_proactive", None) is not None:
            app.state.memory_proactive.set_llm(None)
        return
    llm = OpenAICompatibleClient(settings)
    emotion: EmotionStateMachine = app.state.emotion
    tools: ToolRouter = app.state.tools
    app.state.llm = llm
    app.state.conversation = ConversationManager(
        repo=repo,
        llm=llm,
        emotion=emotion,
        tools=tools,
    )
    if getattr(app.state, "memory_digest", None) is not None:
        app.state.memory_digest.set_llm(llm)
    if getattr(app.state, "memory_proactive", None) is not None:
        app.state.memory_proactive.set_llm(llm)
        app.state.memory_proactive.set_busy_checker(
            lambda: bool(getattr(app.state.conversation, "is_busy", False))
        )


def create_app(db_file: str | None = None) -> FastAPI:
    path = db_file or str(db_path())
    conn = connect(path)
    init_db(conn)
    repo = Repository(conn)
    emotion = EmotionStateMachine()
    tools = ToolRouter()
    scheduler = BackgroundScheduler()
    hub = WsHub()
    reminder = ReminderPlugin(repo, scheduler=scheduler)
    stock = StockPlugin(repo, scheduler=scheduler)
    system = SystemControlPlugin(repo)
    tools.register_plugin(reminder)
    tools.register_plugin(stock)
    tools.register_plugin(system)

    memory_digest = MemoryDigestService(repo, llm=None)
    memory_proactive = MemoryProactiveService(repo, llm=None)
    memory_scheduler = MemoryScheduler(
        repo=repo,
        scheduler=scheduler,
        digest=memory_digest,
        proactive=memory_proactive,
        loop_provider=hub,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        hub.bind_loop(asyncio.get_running_loop())

        def _push_bubble(item_id: int, title: str, message: str) -> None:
            hub.schedule_broadcast(
                {
                    "type": MessageType.REMINDER.value,
                    "payload": {
                        "id": item_id,
                        "message": message,
                        "title": title,
                    },
                }
            )
            hub.schedule_broadcast(
                {
                    "type": MessageType.EMOTION_CHANGED.value,
                    "payload": {"state": "surprised"},
                }
            )

        def _on_reminder(reminder_id: int, message: str) -> None:
            _push_bubble(reminder_id, "提醒", message)

        def _on_stock_alert(watch_id: int, title: str, message: str) -> None:
            _push_bubble(watch_id, title, message)

        def _on_always_on_top(enabled: bool) -> None:
            hub.schedule_broadcast(
                {
                    "type": MessageType.PET_SETTINGS.value,
                    "payload": {"always_on_top": enabled},
                }
            )

        def _on_proactive_ask(title: str, message: str) -> None:
            # Reuse reminder bubble path; negative id avoids colliding with DB reminders
            _push_bubble(-9001, title, message)

        def _on_digest_failure(title: str, message: str) -> None:
            _push_bubble(-9002, title, message)

        reminder.set_notifier(_on_reminder)
        stock.set_notifier(_on_stock_alert)
        system.set_always_on_top_notifier(_on_always_on_top)
        memory_proactive.set_notifier(_on_proactive_ask)
        memory_scheduler.set_digest_failure_notifier(_on_digest_failure)
        memory_proactive.set_busy_checker(
            lambda: bool(
                getattr(getattr(app.state, "conversation", None), "is_busy", False)
            )
        )
        try:
            memory_scheduler.ensure_jobs()
        except Exception:  # noqa: BLE001
            pass
        yield
        if scheduler.running:
            scheduler.shutdown(wait=False)
        conn.close()

    app = FastAPI(title="DexPet Backend", version="0.1.0", lifespan=lifespan)
    app.state = SimpleNamespace(
        repo=repo,
        conn=conn,
        emotion=emotion,
        tools=tools,
        scheduler=scheduler,
        reminder=reminder,
        stock=stock,
        system=system,
        ws_hub=hub,
        llm=None,
        conversation=None,
        memory_digest=memory_digest,
        memory_proactive=memory_proactive,
        memory_scheduler=memory_scheduler,
    )
    rebuild_llm(app)

    app.include_router(http_router)
    app.include_router(ws_router)
    return app
