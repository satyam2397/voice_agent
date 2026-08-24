"""
MCP server: distributor_profile

Every call here MUST take a distributor_id and filter at the query level.
This is the tenant-isolation boundary described in the project spec --
see tests/test_tenant_isolation.py for the concurrent-user check.
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.db.models import DistributorMemory
from app.db.session import SessionLocal

server = Server("distributor_profile")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_distributor_memory",
            description="Fetch the structured profile and rolling summary for one distributor.",
            inputSchema={
                "type": "object",
                "properties": {"distributor_id": {"type": "string"}},
                "required": ["distributor_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "get_distributor_memory":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    session = SessionLocal()
    try:
        memory = (
            session.query(DistributorMemory)
            .filter(DistributorMemory.distributor_id == arguments["distributor_id"])
            .first()
        )
        if memory is None:
            return [TextContent(type="text", text="No memory on file for this distributor yet.")]
        return [TextContent(type="text", text=(
            f"Structured: {memory.structured_fields}\nSummary: {memory.rolling_summary}"
        ))]
    finally:
        session.close()


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
