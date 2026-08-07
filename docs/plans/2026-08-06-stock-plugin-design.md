# Stock Plugin Design

**Goal:** A 股实时行情查询 + 价格/涨跌幅监控气泡提醒。

## Data sources

1. Primary: Tencent quote API (`qt.gtimg.cn` + smartbox name search)
2. Fallback: AKShare when primary fails

## Tools

- `query_stock` — name or code → price, change%, volume
- `watch_stock` — monitor price/change_pct with gte/lte threshold
- `list_stock_watches` / `cancel_stock_watch`

## Monitoring

- APScheduler interval poll (≈60s in session, slower off-hours)
- On trigger: WS `reminder` bubble; keep watch active; 15-minute cooldown per watch
- Persist watches in SQLite; restore on restart
