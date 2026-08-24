"""
MCP client wrapper: discovers tools, hides tenant arguments, dispatches calls.

This is the tenant-isolation boundary. `distributor_id` is a real parameter on
the MCP tool, but it never appears in the schema handed to the model, and the
value used at dispatch always comes from session state.

Why that matters: the model's context contains a live conversation transcript,
which is untrusted input. If the model chose the tenant id, a distributor who
says "actually, pull up the profile for <other id>" would be a prompt-injection
path straight through the isolation boundary. A correctly-scoped WHERE clause
does not help if the value it filters on came from the model.

Stripping the argument makes a cross-tenant request inexpressible rather than
merely discouraged.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp import Client

from app.mcp_servers.tools_server import server as tools_server

log = logging.getLogger("sales_copilot.tools")

# Arguments the orchestrator supplies from session state. Never shown to the
# model, never accepted from it.
INJECTED_ARGS = {"distributor_id"}


class ToolRegistry:
    """
    Owns one MCP client session for the process lifetime.

    Connected in-process (`Client(tools_server)`) rather than over stdio: at
    this scale a subprocess bought startup cost and nothing else. Moving a tool
    out of process later means passing a different transport to Client — the
    orchestrator does not change.
    """

    def __init__(self) -> None:
        self._client: Client | None = None
        self._schemas: list[dict[str, Any]] = []
        # Tools whose tenant argument we stripped, recorded at discovery time so
        # dispatch knows to put it back.
        self._needs_tenant: set[str] = set()

    async def connect(self) -> None:
        self._client = Client(tools_server)
        await self._client.__aenter__()

        listed = await self._client.list_tools()
        self._schemas = []
        self._needs_tenant = set()

        for tool in listed.tools:
            declared = set((tool.input_schema or {}).get("properties") or {})
            if declared & INJECTED_ARGS:
                self._needs_tenant.add(tool.name)
            self._schemas.append(self._public_schema(tool))

        log.info(
            "tools_connected count=%d names=%s tenant_scoped=%s",
            len(self._schemas),
            [s["name"] for s in self._schemas],
            sorted(self._needs_tenant),
        )

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None

    @staticmethod
    def _public_schema(tool: Any) -> dict[str, Any]:
        """Tool schema in Anthropic format, with injected args removed."""
        raw = dict(tool.input_schema or {})
        properties = {
            name: spec
            for name, spec in (raw.get("properties") or {}).items()
            if name not in INJECTED_ARGS
        }
        required = [r for r in (raw.get("required") or []) if r not in INJECTED_ARGS]

        return {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def schemas(self) -> list[dict[str, Any]]:
        return self._schemas

    async def call(
        self, name: str, arguments: dict[str, Any], *, distributor_id: str
    ) -> str:
        """
        Dispatch a tool call, injecting session-owned arguments.

        Anything the model tried to pass for an injected argument is discarded
        before dispatch — not merged, not preferred, discarded.
        """
        if self._client is None:
            return "Tools are unavailable."

        known = {s["name"] for s in self._schemas}
        if name not in known:
            log.warning("unknown_tool name=%s", name)
            return f"Unknown tool: {name}"

        safe_args = {k: v for k, v in (arguments or {}).items() if k not in INJECTED_ARGS}
        if arguments and set(arguments) & INJECTED_ARGS:
            # The model tried to specify a tenant. Worth knowing about.
            log.warning(
                "tenant_arg_from_model_discarded tool=%s keys=%s",
                name,
                sorted(set(arguments) & INJECTED_ARGS),
            )

        if name in self._needs_tenant:
            safe_args["distributor_id"] = distributor_id

        try:
            result = await self._client.call_tool(name, safe_args)
        except Exception as exc:
            log.warning("tool_call_failed tool=%s error=%s", name, exc)
            return f"Tool '{name}' failed: {exc}"

        texts = [
            block.text
            for block in (result.content or [])
            if getattr(block, "type", None) == "text"
        ]
        return "\n".join(texts) if texts else "(tool returned nothing)"
