"""
Spins up two simulated concurrent distributor sessions and asserts that
user A's context never contains user B's data. Cheap, high-value, meant to
be built early rather than as an afterthought -- per project spec section 8f.
"""

import pytest

from app.db.models import DistributorMemory
from app.db.session import SessionLocal


@pytest.fixture
def two_distributors(db_session_factory):
    # TODO: seed two distributors with distinct memory records via the
    # synthetic data generator, return their IDs.
    raise NotImplementedError


async def test_memory_lookup_never_crosses_tenants(two_distributors):
    distributor_a_id, distributor_b_id = two_distributors

    from app.mcp_servers.distributor_profile_server import call_tool

    result_a = await call_tool("get_distributor_memory", {"distributor_id": str(distributor_a_id)})
    result_b = await call_tool("get_distributor_memory", {"distributor_id": str(distributor_b_id)})

    text_a = result_a[0].text
    text_b = result_b[0].text

    session = SessionLocal()
    try:
        memory_b = session.query(DistributorMemory).filter(
            DistributorMemory.distributor_id == distributor_b_id
        ).first()
        assert memory_b.rolling_summary not in text_a
    finally:
        session.close()


async def test_concurrent_sessions_do_not_leak(two_distributors):
    """Fire both lookups concurrently (asyncio.gather) rather than sequentially
    -- this is what actually exercises a shared-mutable-state bug, which a
    sequential test would miss."""
    import asyncio

    from app.mcp_servers.distributor_profile_server import call_tool

    distributor_a_id, distributor_b_id = two_distributors
    result_a, result_b = await asyncio.gather(
        call_tool("get_distributor_memory", {"distributor_id": str(distributor_a_id)}),
        call_tool("get_distributor_memory", {"distributor_id": str(distributor_b_id)}),
    )
    assert result_a != result_b
