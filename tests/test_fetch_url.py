"""Tests for fetch_url (read webpage body)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from backend.core import webpage
from backend.plugins.system_control import SystemControlPlugin


def test_validate_rejects_non_http():
    assert webpage.validate_fetch_url("ftp://example.com")["ok"] is False
    assert webpage.validate_fetch_url("file:///etc/passwd")["ok"] is False
    assert webpage.validate_fetch_url("not-a-url")["ok"] is False


def test_validate_rejects_localhost_and_private():
    for url in (
        "http://localhost/x",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.5/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
    ):
        out = webpage.validate_fetch_url(url)
        assert out["ok"] is False, url
        assert "error" in out


def test_validate_allows_public_https():
    with patch("backend.core.webpage._host_resolves_private", return_value=False):
        out = webpage.validate_fetch_url("https://example.com/path")
        assert out["ok"] is True
        assert out["url"] == "https://example.com/path"


def _mock_stream_client(resp: MagicMock) -> MagicMock:
    client = MagicMock()
    stream_cm = MagicMock()
    stream_cm.__enter__.return_value = resp
    stream_cm.__exit__.return_value = None
    client.stream.return_value = stream_cm
    return client


def test_fetch_url_timeout():
    with (
        patch("backend.core.webpage.validate_fetch_url", return_value={"ok": True, "url": "https://example.com"}),
        patch("backend.core.webpage.httpx.Client") as client_cls,
    ):
        client = MagicMock()
        client_cls.return_value.__enter__.return_value = client
        client.stream.side_effect = httpx.TimeoutException("timed out")
        out = webpage.fetch_url("https://example.com")
        assert out["ok"] is False
        assert "超时" in out["error"] or "timeout" in out["error"].lower()


def test_fetch_url_too_large_content_length():
    with (
        patch("backend.core.webpage.validate_fetch_url", return_value={"ok": True, "url": "https://example.com"}),
        patch("backend.core.webpage.httpx.Client") as client_cls,
    ):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-length": str(webpage.MAX_BYTES + 1)}
        resp.url = httpx.URL("https://example.com")
        resp.is_redirect = False
        resp.content = b"x"
        client_cls.return_value.__enter__.return_value = _mock_stream_client(resp)
        out = webpage.fetch_url("https://example.com")
        assert out["ok"] is False
        assert "过大" in out["error"] or "大" in out["error"]


def test_fetch_url_extracts_and_truncates():
    html = (
        "<html><head><title>Hello Page</title></head>"
        "<body><article><p>" + ("正文内容。" * 3000) + "</p></article></body></html>"
    )
    with (
        patch("backend.core.webpage.validate_fetch_url", return_value={"ok": True, "url": "https://example.com/a"}),
        patch("backend.core.webpage.httpx.Client") as client_cls,
        patch("backend.core.webpage._host_resolves_private", return_value=False),
    ):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {
            "content-type": "text/html; charset=utf-8",
            "content-length": str(len(html.encode())),
        }
        resp.url = httpx.URL("https://example.com/a")
        resp.is_redirect = False
        resp.content = html.encode("utf-8")
        resp.charset_encoding = "utf-8"
        client_cls.return_value.__enter__.return_value = _mock_stream_client(resp)
        out = webpage.fetch_url("https://example.com/a")
        assert out["ok"] is True
        assert out["url"] == "https://example.com/a"
        assert out.get("title") == "Hello Page" or "title" in out
        assert out["text"]
        assert len(out["text"]) <= webpage.MAX_TEXT_CHARS
        assert out.get("truncated") is True


def test_fetch_url_rejects_redirect_to_private():
    with (
        patch("backend.core.webpage.validate_fetch_url") as validate,
        patch("backend.core.webpage.httpx.Client") as client_cls,
    ):
        validate.side_effect = [
            {"ok": True, "url": "https://example.com"},
            {"ok": False, "error": "拒绝访问内网或本机地址"},
        ]
        resp = MagicMock()
        resp.status_code = 302
        resp.headers = {"location": "http://127.0.0.1/secret"}
        resp.url = httpx.URL("https://example.com")
        resp.is_redirect = True
        client_cls.return_value.__enter__.return_value = _mock_stream_client(resp)
        out = webpage.fetch_url("https://example.com")
        assert out["ok"] is False


def test_plugin_exposes_fetch_url():
    plugin = SystemControlPlugin(repo=MagicMock())
    names = {t.name for t in plugin.tools()}
    assert "fetch_url" in names
    tool = next(t for t in plugin.tools() if t.name == "fetch_url")
    assert "网页" in tool.description or "正文" in tool.description
