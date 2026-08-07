"""Fetch public http(s) pages and extract main text (no JS)."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("dexpet.webpage")

MAX_BYTES = 1_500_000  # ~1.5 MiB raw response
MAX_TEXT_CHARS = 10_000
TIMEOUT_SECONDS = 12.0
MAX_REDIRECTS = 5
USER_AGENT = "DexPet/0.1 (+https://github.com/dexpet; read-only fetch)"

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.google.com",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)


def _err(message: str, *, url: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "error": message}
    if url is not None:
        out["url"] = url
    return out


def _hostname_blocked(host: str) -> bool:
    h = host.strip().lower().rstrip(".")
    if not h:
        return True
    if h in _BLOCKED_HOSTNAMES:
        return True
    if h.endswith(".localhost") or h.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(h)
        return not ip.is_global
    except ValueError:
        return False


def _host_resolves_private(host: str) -> bool:
    """True if any resolved address is non-global (private/loopback/link-local/…)."""
    if _hostname_blocked(host):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # fail closed on DNS failure
    if not infos:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if not ip.is_global:
            return True
    return False


def validate_fetch_url(url: str) -> dict[str, Any]:
    """Allow only http(s) URLs that do not target localhost / private networks."""
    raw = (url or "").strip()
    if not raw:
        return _err("URL 为空")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return _err("仅允许 http/https URL", url=raw)
    host = parsed.hostname
    if not host:
        return _err("无效的主机名", url=raw)
    if _host_resolves_private(host):
        return _err("拒绝访问内网或本机地址", url=raw)
    return {"ok": True, "url": raw}


def _extract_text(html: str, url: str) -> tuple[str | None, str | None]:
    """Return (title, text). Prefer trafilatura; fall back to light HTML strip."""
    title: str | None = None
    text: str | None = None
    try:
        import trafilatura

        plain = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
        )
        if plain and plain.strip():
            text = plain.strip()
        meta = trafilatura.extract_metadata(html, default_url=url)
        if meta is not None:
            title = (getattr(meta, "title", None) or "").strip() or None
    except Exception:  # noqa: BLE001
        logger.debug("trafilatura extract failed", exc_info=True)

    if not text:
        text = _fallback_extract(html)
    if not title:
        title = _fallback_title(html)
    return title, text


def _fallback_title(html: str) -> str | None:
    lower = html.lower()
    start = lower.find("<title")
    if start < 0:
        return None
    gt = html.find(">", start)
    end = lower.find("</title>", gt)
    if gt < 0 or end < 0:
        return None
    title = html[gt + 1 : end].strip()
    return title or None


def _fallback_extract(html: str) -> str | None:
    """Minimal tag strip when trafilatura yields nothing."""
    import re

    cleaned = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    cleaned = re.sub(r"(?is)<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _read_body(resp: httpx.Response) -> bytes | dict[str, Any]:
    cl = resp.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_BYTES:
                return _err(f"响应过大（超过 {MAX_BYTES} 字节）", url=str(resp.url))
        except ValueError:
            pass
    # Prefer instance-buffered bytes (tests); never touch httpx .content on streams
    # (that would load the whole body and bypass the size cap).
    inst = getattr(resp, "__dict__", {})
    buffered = inst.get("_content")
    if buffered is None and "content" in inst:
        buffered = inst.get("content")
    if isinstance(buffered, (bytes, bytearray)):
        data = bytes(buffered)
        if len(data) > MAX_BYTES:
            return _err(f"响应过大（超过 {MAX_BYTES} 字节）", url=str(resp.url))
        return data
    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_bytes():
        total += len(chunk)
        if total > MAX_BYTES:
            return _err(f"响应过大（超过 {MAX_BYTES} 字节）", url=str(resp.url))
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_url(url: str) -> dict[str, Any]:
    """GET a public page, extract main text, truncate for LLM context."""
    checked = validate_fetch_url(url)
    if not checked.get("ok"):
        return checked

    current = checked["url"]
    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            },
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                with client.stream("GET", current) as streamed:
                    if streamed.is_redirect:
                        loc = streamed.headers.get("location")
                        if not loc:
                            return _err("重定向缺少 Location", url=current)
                        nxt = urljoin(str(streamed.url), loc)
                        nxt_check = validate_fetch_url(nxt)
                        if not nxt_check.get("ok"):
                            return nxt_check
                        current = nxt_check["url"]
                        continue

                    if streamed.status_code >= 400:
                        return _err(f"HTTP {streamed.status_code}", url=str(streamed.url))

                    body = _read_body(streamed)
                    if isinstance(body, dict):
                        return body

                    ctype = (streamed.headers.get("content-type") or "").lower()
                    head = body.lstrip()[:32].lower()
                    looks_html = head.startswith((b"<!doctype", b"<html", b"<?xml"))
                    if (
                        "html" not in ctype
                        and "text/" not in ctype
                        and "xml" not in ctype
                        and not looks_html
                    ):
                        return _err(
                            f"不支持的内容类型: {ctype or 'unknown'}",
                            url=str(streamed.url),
                        )

                    encoding = streamed.charset_encoding or "utf-8"
                    html = body.decode(encoding, errors="replace")
                    final_url = str(streamed.url)
                    title, text = _extract_text(html, final_url)
                    if not text:
                        return _err("未能抽取到正文", url=final_url)
                    truncated_text, truncated = _truncate(text)
                    result: dict[str, Any] = {
                        "ok": True,
                        "url": final_url,
                        "text": truncated_text,
                        "truncated": truncated,
                    }
                    if title:
                        result["title"] = title
                    return result
            return _err("重定向次数过多", url=current)
    except httpx.TimeoutException:
        return _err("请求超时", url=current)
    except httpx.HTTPError as exc:
        return _err(f"请求失败: {exc}", url=current)
    except Exception as exc:  # noqa: BLE001
        logger.exception("fetch_url failed")
        return _err(f"读取失败: {exc}", url=current)
