"""Stock quote helpers and watch plugin tests."""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from backend.core.stock_quote import (
    StockQuote,
    _parse_tencent_item,
    normalize_symbol,
    resolve_query,
)
from backend.db.repository import Repository
from backend.db.schema import connect, init_db
from backend.plugins.stock import (
    StockPlugin,
    condition_met,
    in_cooldown,
    is_a_share_session,
)


def test_normalize_symbol():
    assert normalize_symbol("600519") == "sh600519"
    assert normalize_symbol("sh600519") == "sh600519"
    assert normalize_symbol("000001") == "sz000001"
    assert normalize_symbol("sz000001") == "sz000001"


def test_parse_tencent_item():
    # Fields 31/32 are change amount / pct in Tencent quote payload
    parts = ["1", "贵州茅台", "600519", "1800.50", "1790.00", "1795.00", "123456"]
    while len(parts) < 33:
        parts.append("0")
    parts[31] = "10.50"
    parts[32] = "0.59"
    raw = 'v_sh600519="' + "~".join(parts) + '";'
    q = _parse_tencent_item(raw)
    assert q is not None
    assert q.symbol == "sh600519"
    assert q.name == "贵州茅台"
    assert q.price == 1800.50
    assert q.change_pct == 0.59
    assert q.volume == 123456


def test_condition_and_cooldown():
    assert condition_met(10, "gte", 10)
    assert condition_met(9.9, "lte", 10)
    assert not condition_met(9.9, "gte", 10)
    now = datetime(2026, 8, 6, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert in_cooldown((now - timedelta(minutes=5)).isoformat(), now=now)
    assert not in_cooldown((now - timedelta(minutes=16)).isoformat(), now=now)


def test_is_a_share_session():
    tz = ZoneInfo("Asia/Shanghai")
    assert is_a_share_session(datetime(2026, 8, 6, 10, 0, tzinfo=tz))  # Thu
    assert not is_a_share_session(datetime(2026, 8, 6, 12, 0, tzinfo=tz))
    assert not is_a_share_session(datetime(2026, 8, 8, 10, 0, tzinfo=tz))  # Sat


def test_resolve_query_code():
    r = resolve_query("600519")
    assert r["symbol"] == "sh600519"


def test_watch_poll_triggers_with_cooldown():
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "t.db")
        init_db(conn)
        repo = Repository(conn)
        alerts: list[tuple] = []
        sched = MagicMock()
        sched.running = True
        plugin = StockPlugin(
            repo,
            scheduler=sched,
            on_alert=lambda i, t, m: alerts.append((i, t, m)),
        )
        wid = repo.create_stock_watch("sh600519", "贵州茅台", "price", "gte", 1000.0)

        quote = StockQuote(
            symbol="sh600519",
            code="600519",
            name="贵州茅台",
            price=1800.0,
            change_pct=1.2,
            change_amount=20.0,
            volume=1000,
            prev_close=1780.0,
            source="test",
        )
        with (
            patch("backend.plugins.stock.is_a_share_session", return_value=True),
            patch("backend.plugins.stock.get_quotes", return_value={"sh600519": quote}),
        ):
            plugin.poll_watches()
            assert len(alerts) == 1
            assert "贵州茅台" in alerts[0][2]
            # cooldown blocks second fire
            plugin.poll_watches()
            assert len(alerts) == 1

        row = repo.get_stock_watch(wid)
        assert row is not None
        assert row["status"] == "active"
        assert row["last_triggered_at"]
        conn.close()
