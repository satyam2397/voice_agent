"""
MCP server exposing the co-pilot's tools.

One server, several tools — a simplification of the original "one MCP server
per tool" plan. Three subprocesses all talking to the same Postgres bought
nothing at this scale except startup cost. Adding a tool is still just adding a
function here, which is the decoupling that mattered.

Runs in-process by default (see orchestrator/tool_registry.py). It is also a
real stdio server — `python -m app.mcp_servers.tools_server` — so moving a tool
out of process later is a transport change, not a rewrite.

TENANT ISOLATION
----------------
`get_distributor_profile` takes a distributor_id, but the orchestrator strips
that argument from the schema the model sees and injects it from session state
(see tool_registry.py). The model cannot express a cross-tenant request because
there is no argument to put one in.
"""

from __future__ import annotations

import uuid

from mcp.server.mcpserver import MCPServer
from sqlalchemy import func, select

from app.db.models import Distributor, DistributorMemory, Fund
from app.db.session import SessionLocal

server = MCPServer(
    name="sales-copilot-tools",
    instructions="Read-only lookups over synthetic fund and distributor data.",
)


def _fund_line(fund: Fund) -> str:
    return (
        f"{fund.name} ({fund.category})\n"
        f"  returns: 1y {fund.return_1y}% | 3y {fund.return_3y}% | 5y {fund.return_5y}%\n"
        f"  expense ratio: {fund.expense_ratio}% | risk: {fund.risk_rating}\n"
        f"  AUM: {fund.aum} cr | benchmark: {fund.benchmark_name}\n"
        f"  manager: {fund.manager_name} | inception: {fund.inception_date:%b %Y}"
    )


@server.tool()
def get_distributor_profile(distributor_id: str) -> str:
    """
    Look up who the rep is talking to: their book, risk appetite, what they have
    raised before, and known objections. Use this to tailor the pitch.
    """
    try:
        tenant = uuid.UUID(distributor_id)
    except (ValueError, AttributeError):
        return "Invalid distributor id."

    session = SessionLocal()
    try:
        # Both reads filter on distributor_id at the query level, never after.
        distributor = session.scalar(
            select(Distributor).where(Distributor.id == tenant)
        )
        if distributor is None:
            return "No distributor on file with that id."

        memory = session.scalar(
            select(DistributorMemory).where(DistributorMemory.distributor_id == tenant)
        )

        lines = [
            f"{distributor.name} — {distributor.region}, {distributor.aum_tier}",
            f"risk appetite: {distributor.risk_appetite}",
            f"prefers: {', '.join(distributor.preferred_asset_classes or []) or 'n/a'}",
            f"relationship since: {distributor.relationship_start_date:%b %Y}",
        ]

        if memory is not None:
            fields = memory.structured_fields or {}
            if topics := fields.get("recent_topics"):
                lines.append(f"recent topics: {', '.join(topics)}")
            if objections := fields.get("known_objections"):
                lines.append(f"known objections: {'; '.join(objections)}")
            if memory.rolling_summary:
                lines.append(f"\nbackground: {memory.rolling_summary}")

        return "\n".join(lines)
    finally:
        session.close()


@server.tool()
def search_funds(category: str = "", max_expense_ratio: float = 0.0, limit: int = 5) -> str:
    """
    Find funds matching a category and/or an expense-ratio ceiling.
    Category is one of: Large Cap, Mid Cap, Small Cap, Debt, Hybrid, Index.
    Use when the distributor asks about a type of fund rather than a named one.
    """
    session = SessionLocal()
    try:
        query = select(Fund)
        if category:
            query = query.where(func.lower(Fund.category) == category.lower())
        if max_expense_ratio > 0:
            query = query.where(Fund.expense_ratio <= max_expense_ratio)
        query = query.order_by(Fund.return_3y.desc()).limit(max(1, min(limit, 10)))

        funds = list(session.scalars(query))
        if not funds:
            return "No funds match those criteria."
        return "\n\n".join(_fund_line(f) for f in funds)
    finally:
        session.close()


@server.tool()
def get_fund_performance(fund_name: str) -> str:
    """
    Get returns, expense ratio, risk rating and AUM for one fund by name.
    Partial names work. Use when a specific fund is named in conversation.
    """
    session = SessionLocal()
    try:
        fund = session.scalar(
            select(Fund).where(Fund.name.ilike(f"%{fund_name}%")).limit(1)
        )
        if fund is None:
            return f"No fund found matching '{fund_name}'."
        return _fund_line(fund)
    finally:
        session.close()


@server.tool()
def compare_funds(fund_name_a: str, fund_name_b: str) -> str:
    """
    Compare two funds side by side on returns, cost and risk.
    Use when the distributor asks how one fund stacks up against another.
    """
    session = SessionLocal()
    try:
        a = session.scalar(select(Fund).where(Fund.name.ilike(f"%{fund_name_a}%")).limit(1))
        b = session.scalar(select(Fund).where(Fund.name.ilike(f"%{fund_name_b}%")).limit(1))

        missing = [n for n, f in ((fund_name_a, a), (fund_name_b, b)) if f is None]
        if missing:
            return f"Could not find: {', '.join(missing)}."

        assert a is not None and b is not None
        rows = [
            ("", a.name, b.name),
            ("category", a.category, b.category),
            ("1y return", f"{a.return_1y}%", f"{b.return_1y}%"),
            ("3y return", f"{a.return_3y}%", f"{b.return_3y}%"),
            ("5y return", f"{a.return_5y}%", f"{b.return_5y}%"),
            ("expense ratio", f"{a.expense_ratio}%", f"{b.expense_ratio}%"),
            ("risk", a.risk_rating, b.risk_rating),
            ("AUM (cr)", str(a.aum), str(b.aum)),
        ]
        width = max(len(r[0]) for r in rows)
        return "\n".join(f"{label:<{width}}  {x}  |  {y}" for label, x, y in rows)
    finally:
        session.close()


if __name__ == "__main__":
    server.run("stdio")
