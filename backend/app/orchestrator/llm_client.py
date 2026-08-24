"""
LLM provider behind one interface, selected by config — not code changes.

LLM_PROVIDER=anthropic for the hosted model, LLM_PROVIDER=ollama for free local
dev. Both return the same LLMResponse so the agent loop never branches on
provider.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import settings


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    text: str | None
    stop_reason: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: Any = None


class LLMClient(Protocol):
    async def complete(
        self, messages: list[dict], tools: list[dict], system: str
    ) -> LLMResponse: ...


def _ssl_context() -> ssl.SSLContext:
    """Use the OS trust store — see stt.py for why (TLS-inspecting proxies)."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())


class AnthropicClient:
    def __init__(self) -> None:
        import httpx
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            http_client=httpx.AsyncClient(verify=_ssl_context()),
        )

    async def complete(
        self, messages: list[dict], tools: list[dict], system: str
    ) -> LLMResponse:
        response = await self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=700,
            system=system,
            messages=messages,
            tools=tools,
        )

        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=dict(b.input or {}))
            for b in response.content
            if b.type == "tool_use"
        ]
        texts = [b.text for b in response.content if b.type == "text"]

        return LLMResponse(
            text="\n".join(texts) if texts else None,
            stop_reason=response.stop_reason or "end_turn",
            tool_calls=tool_calls,
            usage=LLMUsage(response.usage.input_tokens, response.usage.output_tokens),
            raw=response.content,
        )


class OllamaClient:
    """Free local dev. Tool support depends on the model (llama3.1, qwen2.5)."""

    def __init__(self) -> None:
        import ollama

        self._client = ollama.AsyncClient(host=settings.ollama_base_url)

    async def complete(
        self, messages: list[dict], tools: list[dict], system: str
    ) -> LLMResponse:
        # Ollama takes the system prompt as a message, and tool schemas in
        # OpenAI shape rather than Anthropic's.
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

        response = await self._client.chat(
            model=settings.ollama_model,
            messages=[{"role": "system", "content": system}, *messages],
            tools=ollama_tools,
        )

        message = response["message"]
        tool_calls = [
            ToolCall(
                id=f"call_{i}",
                name=tc["function"]["name"],
                input=dict(tc["function"].get("arguments") or {}),
            )
            for i, tc in enumerate(message.get("tool_calls") or [])
        ]

        return LLMResponse(
            text=message.get("content") or None,
            stop_reason="tool_use" if tool_calls else "end_turn",
            tool_calls=tool_calls,
            usage=LLMUsage(
                response.get("prompt_eval_count", 0), response.get("eval_count", 0)
            ),
            raw=message,
        )


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "anthropic":
        return AnthropicClient()
    return OllamaClient()
