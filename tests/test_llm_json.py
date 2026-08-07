"""Tests for robust LLM JSON extraction."""

from __future__ import annotations

import json

import pytest

from backend.core.llm_json import extract_llm_json


def test_extract_plain_object():
    data = extract_llm_json('{"a": 1, "b": "x"}')
    assert data == {"a": 1, "b": "x"}


def test_extract_markdown_fence():
    text = """Here you go:
```json
{
  "daily_markdown": "hello",
  "profile_markdown": "world"
}
```
"""
    data = extract_llm_json(text)
    assert data["daily_markdown"] == "hello"
    assert data["profile_markdown"] == "world"


def test_extract_fence_without_lang_tag():
    text = "```\n{\"ok\": true, \"n\": 2}\n```"
    assert extract_llm_json(text) == {"ok": True, "n": 2}


def test_extract_trailing_comma():
    text = """{
  "daily_markdown": "a",
  "profile_markdown": "b",
  "habits": [{"id": "x", "text": "t",}],
}"""
    data = extract_llm_json(text)
    assert data["daily_markdown"] == "a"
    assert data["habits"][0]["id"] == "x"


def test_extract_prose_around_object():
    text = 'Sure.\n{"daily_markdown": "d", "profile_markdown": "p"}\nThanks!'
    data = extract_llm_json(text)
    assert data["daily_markdown"] == "d"


def test_extract_unescaped_quotes_in_string():
    # Classic CheryFS-GLM failure mode: bare " inside markdown string → Expecting ',' delimiter
    text = """{
  "daily_markdown": "# 日摘要

## 要点
- 用户提到了 "股票" 和提醒
",
  "profile_markdown": "# 关于用户
- 关注 "科技" 股
",
  "open_questions": [],
  "habits": [],
  "fts_facts": ["关注股票"]
}"""
    data = extract_llm_json(text)
    assert "股票" in data["daily_markdown"]
    assert "科技" in data["profile_markdown"]
    assert data["fts_facts"] == ["关注股票"]


def test_extract_literal_newlines_in_string():
    text = '{\n  "daily_markdown": "line1\nline2",\n  "profile_markdown": "p"\n}'
    data = extract_llm_json(text)
    assert data["daily_markdown"] == "line1\nline2"


def test_extract_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        extract_llm_json("   ")


def test_extract_non_object_raises():
    with pytest.raises((json.JSONDecodeError, ValueError)):
        extract_llm_json("[1, 2, 3]")
