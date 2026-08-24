"""
MCP server: fund_data

Exposes read-only lookups over the `funds` table. Standalone process so it
can be added, removed, or scaled independently of the orchestrator.
"""

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from app.db.models import Fund
from app.db.session import SessionLocal

server = Server("fund_data")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_fund_performance",
            description="Look up a fund's returns, expense ratio, and risk rating by name.",
            inputSchema={
                "type": "object",
                "properties": {"fund_name": {"type": "string"}},
                "required": ["fund_name"],
            },
        ),
        Tool(
            name="compare_funds",
            description="Compare two funds' key metrics side by side.",
            inputSchema={
                "type": "object",
                "properties": {
                    "fund_name_a": {"type": "string"},
                    "fund_name_b": {"type": "string"},
                },
                "required": ["fund_name_a", "fund_name_b"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    session = SessionLocal()
    try:
        if name == "get_fund_performance":
            fund = session.query(Fund).filter(Fund.name == arguments["fund_name"]).first()
            if fund is None:
                return [TextContent(type="text", text="No matching fund found.")]
            return [TextContent(type="text", text=(
                f"{fund.name}: 1y {fund.return_1y}%, 3y {fund.return_3y}%, "
                f"5y {fund.return_5y}%, expense ratio {fund.expense_ratio}%, "
                f"risk {fund.risk_rating}"
            ))]

        if name == "compare_funds":
            # TODO: fetch both, format a side-by-side comparison
            return [TextContent(type="text", text="compare_funds not yet implemented")]

        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    finally:
        session.close()


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
