"""A-share quote + threshold watch plugin."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from backend.core.stock_quote import get_quote, get_quotes, normalize_symbol
from backend.core.tools import Plugin, ToolSpec
from backend.db.repository import Repository

StockNotifier = Callable[[int, str, str], None]  # id, title, message

CN_TZ = ZoneInfo("Asia/Shanghai")
COOLDOWN = timedelta(minutes=15)
METRIC_LABEL = {"price": "价格", "change_pct": "涨跌幅"}
OP_LABEL = {"gte": "≥", "lte": "≤"}


def _now_cn() -> datetime:
    return datetime.now(CN_TZ)


def is_a_share_session(now: datetime | None = None) -> bool:
    """Rough CN A-share continuous auction window (incl. lunch gap = False)."""
    dt = now or _now_cn()
    if dt.weekday() >= 5:
        return False
    minutes = dt.hour * 60 + dt.minute
    morning = 9 * 60 + 30 <= minutes <= 11 * 60 + 30
    afternoon = 13 * 60 <= minutes <= 15 * 60
    return morning or afternoon


def condition_met(metric_value: float, op: str, threshold: float) -> bool:
    if op == "gte":
        return metric_value >= threshold
    if op == "lte":
        return metric_value <= threshold
    return False


def in_cooldown(last_triggered_at: str | None, now: datetime | None = None) -> bool:
    if not last_triggered_at:
        return False
    current = now or _now_cn()
    try:
        last = datetime.fromisoformat(last_triggered_at)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=CN_TZ)
    else:
        last = last.astimezone(CN_TZ)
    return current - last < COOLDOWN


class StockPlugin(Plugin):
    name = "stock"

    def __init__(
        self,
        repo: Repository,
        scheduler: BackgroundScheduler | None = None,
        on_alert: StockNotifier | None = None,
        poll_seconds: int = 60,
    ) -> None:
        self.repo = repo
        self.scheduler = scheduler or BackgroundScheduler()
        self.on_alert = on_alert
        self.poll_seconds = poll_seconds
        if not self.scheduler.running:
            self.scheduler.start()
        self._ensure_job()

    def set_notifier(self, on_alert: StockNotifier | None) -> None:
        self.on_alert = on_alert

    def _ensure_job(self) -> None:
        job_id = "stock-watch-poll"
        try:
            self.scheduler.add_job(
                self.poll_watches,
                trigger="interval",
                seconds=self.poll_seconds,
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        except Exception:  # noqa: BLE001
            pass

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="query_stock",
                description=(
                    "查询 A 股实时行情。可用股票名称或代码（如 贵州茅台 / 600519 / sh600519）。"
                    "返回现价、涨跌幅、成交量（手）。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "股票名称或代码",
                        }
                    },
                    "required": ["query"],
                },
                handler=self.query_stock,
            ),
            ToolSpec(
                name="watch_stock",
                description=(
                    "监控某只 A 股：当价格或涨跌幅达到阈值时通过宠物气泡提醒。"
                    "触发后继续监控，同一监控 15 分钟内不重复提醒。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "股票名称或代码",
                        },
                        "metric": {
                            "type": "string",
                            "enum": ["price", "change_pct"],
                            "description": "监控指标：price=现价，change_pct=涨跌幅(%)",
                        },
                        "op": {
                            "type": "string",
                            "enum": ["gte", "lte"],
                            "description": "比较：gte=大于等于，lte=小于等于",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "阈值。涨跌幅用百分数，如 3 表示 3%",
                        },
                    },
                    "required": ["query", "metric", "op", "threshold"],
                },
                handler=self.watch_stock,
            ),
            ToolSpec(
                name="list_stock_watches",
                description="列出股票监控任务。默认仅 active。",
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["active", "cancelled"],
                            "description": "可选状态过滤",
                        }
                    },
                },
                handler=self.list_stock_watches,
            ),
            ToolSpec(
                name="cancel_stock_watch",
                description="按 id 取消股票监控。",
                parameters={
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "监控 ID"},
                    },
                    "required": ["id"],
                },
                handler=self.cancel_stock_watch,
            ),
        ]

    def query_stock(self, query: str) -> dict[str, Any]:
        return get_quote(query)

    def watch_stock(
        self,
        query: str,
        metric: str,
        op: str,
        threshold: float,
    ) -> dict[str, Any]:
        if metric not in {"price", "change_pct"}:
            return {"error": "metric 必须是 price 或 change_pct"}
        if op not in {"gte", "lte"}:
            return {"error": "op 必须是 gte 或 lte"}
        info = get_quote(query)
        if info.get("error") and not info.get("quote"):
            return info
        quote = info.get("quote") or {}
        symbol = quote.get("symbol") or normalize_symbol(query)
        if not symbol:
            return info
        name = str(quote.get("name") or symbol)
        wid = self.repo.create_stock_watch(
            symbol=symbol,
            name=name,
            metric=metric,
            op=op,
            threshold=float(threshold),
        )
        return {
            "id": wid,
            "symbol": symbol,
            "name": name,
            "metric": metric,
            "op": op,
            "threshold": float(threshold),
            "status": "active",
            "cooldown_minutes": 15,
            "message": (
                f"已监控 {name}({symbol})："
                f"{METRIC_LABEL[metric]}{OP_LABEL[op]}{threshold}"
                f"{'%' if metric == 'change_pct' else ''}"
            ),
        }

    def list_stock_watches(self, status: str | None = "active") -> list[dict[str, Any]]:
        return self.repo.list_stock_watches(status=status)

    def cancel_stock_watch(self, id: int) -> dict[str, Any]:
        ok = self.repo.cancel_stock_watch(id)
        return {"deleted": ok, "id": id, "status": "cancelled" if ok else "not_found"}

    def poll_watches(self) -> None:
        watches = self.repo.list_stock_watches(status="active")
        if not watches:
            return
        # Off-hours: still allow poll but less critical; skip network if closed
        if not is_a_share_session():
            return
        symbols = sorted({w["symbol"] for w in watches})
        try:
            quotes = get_quotes(symbols)
        except Exception:  # noqa: BLE001
            return
        now = _now_cn()
        for watch in watches:
            quote = quotes.get(watch["symbol"])
            if quote is None:
                continue
            metric = watch["metric"]
            value = quote.price if metric == "price" else quote.change_pct
            if not condition_met(float(value), watch["op"], float(watch["threshold"])):
                continue
            if in_cooldown(watch.get("last_triggered_at"), now=now):
                continue
            unit = "%" if metric == "change_pct" else ""
            title = "股价提醒"
            message = (
                f"{quote.name}({quote.symbol}) "
                f"现价 {quote.price:.2f}，涨跌幅 {quote.change_pct:+.2f}%，"
                f"成交量 {quote.volume} 手。"
                f"触发条件：{METRIC_LABEL.get(metric, metric)}"
                f"{OP_LABEL.get(watch['op'], watch['op'])}"
                f"{watch['threshold']}{unit}"
            )
            self.repo.touch_stock_watch_triggered(watch["id"], when=now.isoformat())
            if self.on_alert is not None:
                try:
                    self.on_alert(int(watch["id"]), title, message)
                except Exception:  # noqa: BLE001
                    pass
