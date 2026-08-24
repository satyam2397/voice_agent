"""
Hand-rolled agent loop -- deliberately not LangChain/LangGraph.

Why: this is a single orchestrator (not multi-agent), so there is no
branching graph to manage. The loop is: call the LLM with tools -> if it
asks for a tool, run it via MCP and feed the result back -> repeat until it
returns text. Native tool-use + MCP already cover the two things a
framework would otherwise buy us (tool orchestration, tool decoupling).

Swappable LLM provider: see app.orchestrator.llm_client.
"""

import time

from app.orchestrator.llm_client import LLMClient
from app.orchestrator.mcp_client import MCPToolRegistry


class AgentOrchestrator:
    def __init__(self, llm_client: LLMClient, tool_registry: MCPToolRegistry, max_turns: int = 5):
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_turns = max_turns

    async def run(self, context: dict) -> dict:
        """
        context: recent conversation window + distributor profile summary
        + retrieved fund data/documents, assembled upstream.

        Returns a dict with the flash card content plus timing/token
        metadata for logging into flash_cards.
        """
        start = time.monotonic()
        messages = [{"role": "user", "content": self._build_prompt(context)}]
        tools = self.tool_registry.list_tool_schemas()

        input_tokens = 0
        output_tokens = 0
        tool_calls_used = []

        for _ in range(self.max_turns):
            response = await self.llm_client.complete(messages=messages, tools=tools)
            input_tokens += response.usage.input_tokens
            output_tokens += response.usage.output_tokens

            if response.stop_reason != "tool_use":
                return {
                    "content": response.text,
                    "tool_calls_used": tool_calls_used,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": int((time.monotonic() - start) * 1000),
                }

            for tool_call in response.tool_calls:
                result = await self.tool_registry.call(tool_call.name, tool_call.input)
                tool_calls_used.append({"tool": tool_call.name, "input": tool_call.input})
                messages.append({"role": "assistant", "content": response.raw})
                messages.append(
                    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_call.id, "content": result}]}
                )

        # Hit max_turns without a final answer -- fail closed, don't hallucinate.
        return {
            "content": None,
            "tool_calls_used": tool_calls_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "error": "max_turns_exceeded",
        }

    @staticmethod
    def _build_prompt(context: dict) -> str:
        return (
            "You are a sales co-pilot. Using only the provided context and "
            "tool calls, produce a short, actionable flash card for the rep. "
            "If the data is missing or malformed, say so -- never invent numbers.\n\n"
            f"Context:\n{context}"
        )
