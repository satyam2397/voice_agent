"""
Exercises the tool layer and the agent loop without needing an LLM provider.

Three things get checked:
  1. tools are discovered and callable through MCP
  2. distributor_id never appears in the schema handed to the model
  3. a tenant id supplied *by the model* is discarded, not honoured

Run:  ./.venv/bin/python scripts/agent_smoke.py
"""

import asyncio
import json
import sys

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

from app.db.models import Distributor  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.orchestrator.agent import Agent  # noqa: E402
from app.orchestrator.llm_client import LLMResponse, LLMUsage, ToolCall  # noqa: E402
from app.orchestrator.tool_registry import ToolRegistry  # noqa: E402


class ScriptedLLM:
    """Replays a fixed sequence of responses so the loop runs without an API."""

    def __init__(self, script: list[LLMResponse]) -> None:
        self._script = list(script)
        self.seen_tools: list[dict] = []

    async def complete(self, messages, tools, system):  # noqa: ANN001
        self.seen_tools = tools
        return self._script.pop(0) if self._script else LLMResponse(
            text="(no more scripted responses)", stop_reason="end_turn"
        )


def two_distributors() -> tuple[str, str, str, str]:
    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Distributor).order_by(Distributor.name)))
        assert len(rows) >= 2, "seed the database first: scripts/seed_data.py"
        return str(rows[0].id), rows[0].name, str(rows[1].id), rows[1].name
    finally:
        session.close()


async def main() -> int:
    a_id, a_name, b_id, b_name = two_distributors()
    print(f"tenant A: {a_name}\ntenant B: {b_name}\n")

    tools = ToolRegistry()
    await tools.connect()
    failures = []

    # --- 1. discovery -----------------------------------------------------
    schemas = tools.schemas()
    print(f"discovered {len(schemas)} tools: {[s['name'] for s in schemas]}\n")
    if not schemas:
        failures.append("no tools discovered")

    # --- 2. tenant arg must not be visible to the model -------------------
    leaked = [
        s["name"]
        for s in schemas
        if "distributor_id" in (s["input_schema"].get("properties") or {})
    ]
    if leaked:
        failures.append(f"distributor_id exposed in schema for: {leaked}")
    else:
        print("OK  distributor_id absent from every tool schema shown to the model")

    # --- 3. profile lookup is scoped to the injected tenant ---------------
    profile_a = await tools.call("get_distributor_profile", {}, distributor_id=a_id)
    profile_b = await tools.call("get_distributor_profile", {}, distributor_id=b_id)

    if a_name not in profile_a:
        failures.append("tenant A profile did not contain tenant A")
    if b_name in profile_a:
        failures.append("LEAK: tenant B data present in tenant A's profile")
    if not failures:
        print("OK  each tenant sees only their own profile")

    # --- 4. a model-supplied tenant id must be ignored --------------------
    hijack = await tools.call(
        "get_distributor_profile",
        {"distributor_id": b_id},   # the model trying to pick a tenant
        distributor_id=a_id,        # session says otherwise
    )
    if b_name in hijack:
        failures.append("LEAK: model-supplied distributor_id overrode session tenant")
    elif a_name in hijack:
        print("OK  model-supplied distributor_id discarded; session tenant won")

    # --- 5. agent loop drives tools and produces a card -------------------
    llm = ScriptedLLM([
        LLMResponse(
            text=None,
            stop_reason="tool_use",
            tool_calls=[
                ToolCall(id="t1", name="get_distributor_profile", input={}),
                ToolCall(
                    id="t2",
                    name="search_funds",
                    input={"category": "Debt", "limit": 2},
                ),
            ],
            usage=LLMUsage(120, 40),
            raw=[{"type": "text", "text": "calling tools"}],
        ),
        LLMResponse(
            text="Silverpine Debt Focused Fund: 6.73% 1y, 0.23% expense ratio.",
            stop_reason="end_turn",
            usage=LLMUsage(300, 30),
        ),
    ])

    agent = Agent(llm, tools)  # type: ignore[arg-type]
    result = await agent.run(
        conversation="[distributor] What debt options do you have that aren't expensive?",
        trigger_reason="keyword:expense",
        distributor_id=a_id,
    )

    print(f"\nagent card    : {result.content}")
    print(f"tools used    : {[t['tool'] for t in result.tool_calls]}")
    print(f"tokens        : {result.input_tokens} in / {result.output_tokens} out")
    print(f"latency       : {result.latency_ms} ms")
    print(f"error         : {result.error}")

    if result.error:
        failures.append(f"agent errored: {result.error}")
    if len(result.tool_calls) != 2:
        failures.append(f"expected 2 tool calls, got {len(result.tool_calls)}")

    # The schema the loop actually handed the model must also be clean.
    if any(
        "distributor_id" in (t["input_schema"].get("properties") or {})
        for t in llm.seen_tools
    ):
        failures.append("distributor_id reached the model via the agent loop")

    await tools.close()

    print("\n" + "=" * 60)
    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS — tools, tenant isolation, and the agent loop all behave")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
