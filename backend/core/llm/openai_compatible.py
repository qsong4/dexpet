"""OpenAI Chat Completions compatible LLM client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError

from backend.paths import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

# Defaults tuned for local/VPN gateways: fail connect sooner than SDK read default,
# keep read long enough for slow local models, limit retries so UI isn't stuck on Thinking.
DEFAULT_CONNECT_TIMEOUT = 15.0
DEFAULT_READ_TIMEOUT = 180.0
DEFAULT_MAX_RETRIES = 1


@dataclass
class LLMSettings:
    provider_preset: str = "deepseek"
    base_url: str = DEEPSEEK_BASE_URL
    model: str = DEEPSEEK_MODEL
    api_key: str = ""
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    read_timeout: float = DEFAULT_READ_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES

    @classmethod
    def deepseek(cls, api_key: str) -> LLMSettings:
        return cls(
            provider_preset="deepseek",
            base_url=DEEPSEEK_BASE_URL,
            model=DEEPSEEK_MODEL,
            api_key=api_key,
        )


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ChatResult:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


class OpenAICompatibleClient:
    def __init__(self, settings: LLMSettings, client: AsyncOpenAI | None = None) -> None:
        if not settings.api_key:
            raise ValueError("api_key is required")
        self.settings = settings
        # Use base_url exactly as configured. Do NOT auto-append /v1 —
        # custom gateways often already include a full prefix (e.g. .../api/v1/code).
        base = settings.base_url.rstrip("/")
        self._client = client or AsyncOpenAI(
            api_key=settings.api_key,
            base_url=base,
            timeout=self._timeout_config(settings),
            max_retries=max(0, int(settings.max_retries)),
        )

    @staticmethod
    def _timeout_config(settings: LLMSettings) -> Any:
        # httpx.Timeout accepts connect/read/write/pool; openai accepts the same.
        from httpx import Timeout

        connect = max(1.0, float(settings.connect_timeout))
        read = max(connect, float(settings.read_timeout))
        return Timeout(connect=connect, read=read, write=read, pool=connect)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> ChatResult:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._format_api_error(exc)) from exc
        choice = resp.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments or "{}",
                    )
                )
        return ChatResult(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Yield text deltas. Tool-call streaming is not used in MVP stream path."""
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(self._format_api_error(exc)) from exc
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def _format_api_error(self, exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        base = self.settings.base_url.rstrip("/")
        endpoint = f"{base}/chat/completions"
        detail = str(exc)
        if status == 404:
            return (
                f"API 返回 404（地址不存在）。请检查 Base URL。\n"
                f"实际请求：{endpoint}\n"
                f"提示：Base URL 应填到 chat completions 的前缀"
                f"（不要多加 /v1），例如 https://host/api/v1/code"
            )
        if self._is_timeout_or_unreachable(exc, detail):
            return (
                f"API 调用失败：连接超时/不可达。\n"
                f"实际请求：{endpoint}\n"
                f"模型：{self.settings.model}\n"
                f"提示：请检查内网/VPN，或在设置中切换到其他可用模型 profile。"
            )
        if status:
            return f"API 错误 {status}：{detail}"
        return f"API 调用失败：{detail}"

    @staticmethod
    def _is_timeout_or_unreachable(exc: Exception, detail: str) -> bool:
        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            return True
        # Unwrap RuntimeError/Cause chains and httpx errors by text when types differ.
        lowered = detail.lower()
        needles = (
            "timeout",
            "timed out",
            "connecterror",
            "connection error",
            "connection refused",
            "nodename nor servname",
            "name or service not known",
            "network is unreachable",
        )
        return any(n in lowered for n in needles)
