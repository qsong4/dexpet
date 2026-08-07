"""Robust JSON extraction helpers for LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_code_fence(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    fence = _FENCE_RE.search(raw)
    if fence:
        return fence.group(1).strip()
    # Opening fence without closing (common truncation / model habit)
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


def _slice_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    return text[start : end + 1]


def _fix_trailing_commas(text: str) -> str:
    prev = None
    cur = text
    # Repeat: nested trailing commas can remain after one pass in rare cases
    while prev != cur:
        prev = cur
        cur = _TRAILING_COMMA_RE.sub(r"\1", cur)
    return cur


def _looks_like_string_end(text: str, quote_idx: int) -> bool:
    """Heuristic: quote ends a JSON string if next non-ws is structural."""
    j = quote_idx + 1
    n = len(text)
    while j < n and text[j] in " \t\r\n":
        j += 1
    if j >= n:
        return True
    return text[j] in ",}]:"


def _escape_invalid_string_chars(text: str) -> str:
    """Escape raw control chars / unescaped quotes inside JSON string literals."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\":
            out.append(ch)
            escape = True
            i += 1
            continue

        if ch == '"':
            if _looks_like_string_end(text, i):
                in_string = False
                out.append(ch)
            else:
                out.append('\\"')
            i += 1
            continue

        if ch == "\n":
            out.append("\\n")
            i += 1
            continue
        if ch == "\r":
            out.append("\\r")
            i += 1
            continue
        if ch == "\t":
            out.append("\\t")
            i += 1
            continue
        if ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
            i += 1
            continue

        out.append(ch)
        i += 1
    return "".join(out)


def _normalize_candidates(text: str) -> list[str]:
    base = _strip_code_fence(text)
    if not base:
        return []
    try:
        sliced = _slice_object(base)
    except ValueError:
        sliced = base
    candidates = [base, sliced]
    repaired: list[str] = []
    for cand in candidates:
        fixed = _fix_trailing_commas(cand)
        repaired.append(fixed)
        repaired.append(_escape_invalid_string_chars(fixed))
        repaired.append(_escape_invalid_string_chars(cand))
    # Preserve order, drop duplicates
    seen: set[str] = set()
    out: list[str] = []
    for c in repaired:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def extract_llm_json(text: str) -> dict[str, Any]:
    """Parse a JSON object from noisy LLM output (fences, prose, trailing commas)."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty LLM response")

    last_err: Exception | None = None
    for candidate in _normalize_candidates(raw):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
        if isinstance(data, dict):
            return data
        last_err = ValueError("LLM JSON must be object")

    if last_err is not None:
        raise last_err
    raise ValueError("failed to parse LLM JSON")
