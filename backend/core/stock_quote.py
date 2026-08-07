"""A-share quote client: Tencent primary, AKShare fallback."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import quote

import httpx

TENCENT_QUOTE = "https://qt.gtimg.cn/q={symbols}"
TENCENT_SUGGEST = "https://smartbox.gtimg.cn/s3/?v=2&q={q}&t=all"

# sh600519 / sz000001 / bj430047
_CODE_RE = re.compile(
    r"^(?:(?P<mkt>sh|sz|bj))?(?P<code>\d{6})$",
    re.IGNORECASE,
)


@dataclass
class StockQuote:
    symbol: str  # sh600519
    code: str  # 600519
    name: str
    price: float
    change_pct: float
    change_amount: float
    volume: int  # 手
    prev_close: float
    source: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["volume_hands"] = d.pop("volume")
        return d


def normalize_symbol(raw: str) -> str | None:
    text = raw.strip().lower().replace(".", "")
    text = text.replace("沪", "sh").replace("深", "sz").replace("北", "bj")
    m = _CODE_RE.match(text)
    if not m:
        return None
    code = m.group("code")
    mkt = m.group("mkt")
    if mkt:
        return f"{mkt}{code}"
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sz{code}"


def _parse_tencent_item(raw: str) -> StockQuote | None:
    # v_sh600519="1~贵州茅台~600519~1855.00~..."
    if '="' not in raw:
        return None
    body = raw.split('="', 1)[1].rstrip('";\n\r ')
    parts = body.split("~")
    if len(parts) < 33:
        return None
    try:
        name = parts[1]
        code = parts[2]
        price = float(parts[3] or 0)
        prev_close = float(parts[4] or 0)
        volume = int(float(parts[6] or 0))
        change_amount = float(parts[31] or 0)
        change_pct = float(parts[32] or 0)
    except (ValueError, IndexError):
        return None
    if not code or price <= 0:
        return None
    symbol = normalize_symbol(code) or f"sh{code}"
    # Prefer market from variable name if present
    left = raw.split("=", 1)[0]
    m = re.search(r"v_((?:sh|sz|bj)\d{6})", left, re.I)
    if m:
        symbol = m.group(1).lower()
    return StockQuote(
        symbol=symbol,
        code=code,
        name=name,
        price=price,
        change_pct=change_pct,
        change_amount=change_amount,
        volume=volume,
        prev_close=prev_close,
        source="tencent",
    )


def fetch_tencent_quotes(symbols: list[str], timeout: float = 8.0) -> dict[str, StockQuote]:
    if not symbols:
        return {}
    uniq = []
    seen: set[str] = set()
    for s in symbols:
        ns = normalize_symbol(s)
        if ns and ns not in seen:
            seen.add(ns)
            uniq.append(ns)
    if not uniq:
        return {}
    url = TENCENT_QUOTE.format(symbols=",".join(uniq))
    with httpx.Client(timeout=timeout, headers={"User-Agent": "DexPet/0.1"}) as client:
        resp = client.get(url)
        resp.raise_for_status()
        resp.encoding = "gbk"
        text = resp.text
    out: dict[str, StockQuote] = {}
    for chunk in text.strip().split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        q = _parse_tencent_item(chunk)
        if q:
            out[q.symbol] = q
    return out


def suggest_tencent(query: str, limit: int = 8, timeout: float = 8.0) -> list[dict[str, str]]:
    q = query.strip()
    if not q:
        return []
    url = TENCENT_SUGGEST.format(q=quote(q))
    with httpx.Client(timeout=timeout, headers={"User-Agent": "DexPet/0.1"}) as client:
        resp = client.get(url)
        resp.raise_for_status()
        text = resp.text
    # v_hint="茅台~sh~600519~贵州茅台^茅台~sz~..."
    if '="' not in text:
        return []
    body = text.split('="', 1)[1].rstrip('";\n\r ')
    results: list[dict[str, str]] = []
    for item in body.split("^"):
        parts = item.split("~")
        if len(parts) < 4:
            continue
        # formats vary: q~mkt~code~name  or  name~mkt~code~name
        mkt = parts[1].lower()
        code = parts[2]
        name = parts[3] if len(parts) > 3 else parts[0]
        if mkt not in {"sh", "sz", "bj"} or not code.isdigit():
            continue
        symbol = f"{mkt}{code}"
        results.append({"symbol": symbol, "code": code, "name": name, "market": mkt})
        if len(results) >= limit:
            break
    return results


def _eastmoney_quote_httpx(code: str, symbol: str) -> StockQuote | None:
    """East Money quote via httpx (same endpoint AKShare stock_bid_ask_em uses)."""
    market_code = 1 if code.startswith("6") else 0
    # push2 often disconnects; push2delay is more reliable from some networks
    urls = (
        "https://push2delay.eastmoney.com/api/qt/stock/get",
        "https://push2.eastmoney.com/api/qt/stock/get",
    )
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f43,f57,f58,f169,f170,f47,f60",
        "secid": f"{market_code}.{code}",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DexPet/0.1",
        "Referer": "https://quote.eastmoney.com/",
    }
    for url in urls:
        for _ in range(2):
            try:
                with httpx.Client(timeout=10.0, headers=headers) as client:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    data = (resp.json() or {}).get("data") or {}
                price = float(data.get("f43") or 0)
                if price <= 0:
                    continue
                return StockQuote(
                    symbol=symbol,
                    code=str(data.get("f57") or code),
                    name=str(data.get("f58") or code),
                    price=price,
                    change_pct=float(data.get("f170") or 0),
                    change_amount=float(data.get("f169") or 0),
                    volume=int(float(data.get("f47") or 0)),
                    prev_close=float(data.get("f60") or 0),
                    source="akshare",
                )
            except Exception:  # noqa: BLE001
                continue
    return None


def fetch_akshare_quote(symbol: str) -> StockQuote | None:
    """Fallback quote: East Money (AKShare stack), with httpx then akshare lib."""
    ns = normalize_symbol(symbol)
    if not ns:
        return None
    code = ns[2:]

    # 1) Direct East Money (more resilient than akshare's bare requests)
    q = _eastmoney_quote_httpx(code, ns)
    if q is not None:
        return q

    # 2) AKShare library paths
    try:
        import akshare as ak  # type: ignore
    except Exception:  # noqa: BLE001
        return None

    try:
        df = ak.stock_bid_ask_em(symbol=code)
        mapping = {str(a): b for a, b in zip(df.iloc[:, 0], df.iloc[:, 1], strict=False)}
        price = float(mapping.get("最新") or 0)
        if price > 0:
            return StockQuote(
                symbol=ns,
                code=code,
                name=str(mapping.get("名称") or code),
                price=price,
                change_pct=float(mapping.get("涨幅") or 0),
                change_amount=float(mapping.get("涨跌") or 0),
                volume=int(float(mapping.get("总手") or 0)),
                prev_close=float(mapping.get("昨收") or 0),
                source="akshare",
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"].astype(str) == code]
        if row.empty:
            return None
        r = row.iloc[0]
        price = float(r["最新价"])
        change_amount = float(r.get("涨跌额", 0) or 0)
        prev = float(r["昨收"]) if "昨收" in r and r["昨收"] == r["昨收"] else price - change_amount
        return StockQuote(
            symbol=ns,
            code=code,
            name=str(r.get("名称", code)),
            price=price,
            change_pct=float(r["涨跌幅"]),
            change_amount=change_amount,
            volume=int(float(r.get("成交量", 0) or 0)),
            prev_close=float(prev),
            source="akshare",
        )
    except Exception:  # noqa: BLE001
        return None


def suggest_akshare(query: str, limit: int = 8) -> list[dict[str, str]]:
    try:
        import akshare as ak  # type: ignore
    except Exception:  # noqa: BLE001
        return []
    q = query.strip()
    if not q:
        return []
    try:
        df = ak.stock_info_a_code_name()
    except Exception:  # noqa: BLE001
        return []
    try:
        codes = df["code"].astype(str)
        names = df["name"].astype(str)
    except Exception:  # noqa: BLE001
        # alternate column names
        cols = {c.lower(): c for c in df.columns}
        code_col = cols.get("code") or cols.get("代码")
        name_col = cols.get("name") or cols.get("名称")
        if not code_col or not name_col:
            return []
        codes = df[code_col].astype(str)
        names = df[name_col].astype(str)
    hits: list[dict[str, str]] = []
    for code, name in zip(codes, names, strict=False):
        if q in name or q == code:
            symbol = normalize_symbol(code)
            if not symbol:
                continue
            hits.append(
                {
                    "symbol": symbol,
                    "code": code,
                    "name": name,
                    "market": symbol[:2],
                }
            )
            if len(hits) >= limit:
                break
    return hits


def resolve_query(query: str) -> dict[str, Any]:
    """Resolve name/code to a single symbol or candidate list."""
    q = query.strip()
    symbol = normalize_symbol(q)
    if symbol:
        return {"symbol": symbol, "candidates": []}
    candidates = suggest_tencent(q)
    if not candidates:
        candidates = suggest_akshare(q)
    if len(candidates) == 1:
        return {"symbol": candidates[0]["symbol"], "candidates": candidates}
    if not candidates:
        return {"symbol": None, "candidates": [], "error": f"未找到股票：{q}"}
    return {"symbol": None, "candidates": candidates, "error": "匹配到多只股票，请用代码指定"}


def get_quote(query: str) -> dict[str, Any]:
    resolved = resolve_query(query)
    symbol = resolved.get("symbol")
    if not symbol:
        return resolved
    quotes = fetch_tencent_quotes([symbol])
    quote = quotes.get(symbol)
    if quote is None:
        quote = fetch_akshare_quote(symbol)
    if quote is None:
        return {
            "symbol": symbol,
            "candidates": resolved.get("candidates") or [],
            "error": f"无法获取行情：{symbol}",
        }
    return {"quote": quote.to_dict(), "candidates": resolved.get("candidates") or []}


def get_quotes(symbols: list[str]) -> dict[str, StockQuote]:
    result = fetch_tencent_quotes(symbols)
    missing = [s for s in symbols if normalize_symbol(s) not in result]
    for s in missing:
        q = fetch_akshare_quote(s)
        if q:
            result[q.symbol] = q
    return result
