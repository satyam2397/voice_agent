"""
The agent loop: call the model with tools, run whatever it asks for, feed the
results back, repeat until it produces a flash card.

Hand-rolled rather than LangChain/LangGraph. There is one orchestrator and no
branching graph, so a framework would add indirection without removing work —
and every step between a trigger and a card stays something you can read.

Fails closed everywhere: timeouts, malformed tool output, and running out of
turns all produce "no card" rather than a guess.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.config import settings
from app.orchestrator.llm_client import LLMClient
from app.orchestrator.tool_registry import ToolRegistry

log = logging.getLogger("sales_copilot.agent")

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """\
You are a real-time sales co-pilot for a mutual fund distribution rep who is \
mid-conversation with a distributor. You are not in the conversation. You write \
a short note the rep can glance at while still talking.

Rules:
- Use the tools to get real numbers. Never invent a figure, fund name, or fact.
- If the tools do not have what is needed, say so in one line. Do not guess.
- Call get_distributor_profile when who you are talking to changes the answer.
- Be brief: 2-3 sentences, or a couple of short lines. The rep is reading this \
while someone is talking to them.
- Lead with the number or fact that answers the question. No preamble, no \
"here's a summary", no restating the question.
- Plain text only. No markdown headers or bullet syntax.
"""


@dataclass
class FlashCardResult:
    content: str | None
    trigger_reason: str
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    error: str | None = None


class Agent:
    def __init__(self, llm: LLMClient, tools: ToolRegistry) -> None:
        self._llm = llm
        self._tools = tools

    async def run(
        self,
        *,
        conversation: str,
        trigger_reason: str,
        distributor_id: str,
    ) -> FlashCardResult:
        started = time.monotonic()
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Recent conversation:\n{conversation}\n\n"
                    f"The distributor's last turn warrants help ({trigger_reason}). "
                    f"Write the flash card."
                ),
            }
        ]

        used: list[dict] = []
        tokens_in = tokens_out = 0

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = await asyncio.wait_for(
                    self._llm.complete(
                        messages=messages,
                        tools=self._tools.schemas(),
                        system=SYSTEM_PROMPT,
                    ),
                    timeout=settings.agent_timeout_s,
                )
                tokens_in += response.usage.input_tokens
                tokens_out += response.usage.output_tokens

                if not response.tool_calls:
                    return FlashCardResult(
                        content=(response.text or "").strip() or None,
                        trigger_reason=trigger_reason,
                        tool_calls=used,
                        input_tokens=tokens_in,
                        output_tokens=tokens_out,
                        latency_ms=_ms_since(started),
                    )

                messages.append({"role": "assistant", "content": response.raw})

                results = []
                for call in response.tool_calls:
                    output = await self._tools.call(
                        call.name, call.input, distributor_id=distributor_id
                    )
                    used.append({"tool": call.name, "input": call.input})
                    log.info(
                        "tool_used name=%s args=%s chars=%d",
                        call.name,
                        call.input,
                        len(output),
                    )
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": output,
                        }
                    )
                messages.append({"role": "user", "content": results})

            # Ran out of rounds without settling on an answer.
            return FlashCardResult(
                content=None,
                trigger_reason=trigger_reason,
                tool_calls=used,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                latency_ms=_ms_since(started),
                error="max_tool_rounds_exceeded",
            )

        except asyncio.TimeoutError:
            log.warning("agent_timeout after=%dms", _ms_since(started))
            return FlashCardResult(
                content=None,
                trigger_reason=trigger_reason,
                tool_calls=used,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                latency_ms=_ms_since(started),
                error="llm_timeout",
            )
        except Exception as exc:
            log.exception("agent_failed")
            return FlashCardResult(
                content=None,
                trigger_reason=trigger_reason,
                tool_calls=used,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                latency_ms=_ms_since(started),
                error=f"{type(exc).__name__}: {exc}",
            )


def _ms_since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
