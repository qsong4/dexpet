"""Long-term memory via SQLite FTS5."""

from __future__ import annotations

import re
import sqlite3
from typing import Any


FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    content,
    kind,
    created_at,
    tokenize = 'unicode61'
);
"""


def init_memory(conn: sqlite3.Connection) -> None:
    conn.executescript(FTS_SCHEMA)
    conn.commit()


def add_memory(
    conn: sqlite3.Connection,
    content: str,
    kind: str = "dialogue",
    created_at: str | None = None,
) -> None:
    text = (content or "").strip()
    if not text:
        return
    from datetime import datetime, timezone

    ts = created_at or datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO memory_fts (content, kind, created_at) VALUES (?, ?, ?)",
        (text[:2000], kind, ts),
    )
    conn.commit()


def _fts_query(raw: str) -> str:
    # Build a safe OR query from tokens; strip quotes.
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", raw, flags=re.UNICODE)
    tokens = [t for t in tokens if len(t) >= 1][:12]
    if not tokens:
        return ""
    parts = []
    for t in tokens:
        safe = t.replace('"', "")
        if safe:
            parts.append(f'"{safe}"')
    return " OR ".join(parts)


def search_memory(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[dict[str, Any]]:
    q = _fts_query(query)
    hits: list[dict[str, Any]] = []
    if q:
        try:
            rows = conn.execute(
                """
                SELECT content, kind, created_at
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (q, limit),
            ).fetchall()
            hits = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            hits = []

    if hits:
        return hits

    # Fallback: substring match (better for Chinese without a CJK tokenizer)
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query or "", flags=re.UNICODE)
    tokens = [t for t in tokens if len(t) >= 1][:6]
    if not tokens:
        rows = conn.execute(
            "SELECT content, kind, created_at FROM memory_fts ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    clauses = " OR ".join(["content LIKE ?" for _ in tokens])
    params: list[Any] = [f"%{t}%" for t in tokens]
    params.append(limit)
    rows = conn.execute(
        f"""
        SELECT content, kind, created_at
        FROM memory_fts
        WHERE {clauses}
        ORDER BY rowid DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def format_memory_block(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    lines = ["以下是与用户相关的长期记忆片段，请在回答时酌情参考："]
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. ({hit.get('kind', 'note')}) {hit.get('content', '')}")
    return "\n".join(lines)
