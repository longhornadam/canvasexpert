"""Contract test for api/mcp_server/contract.py.

A shape agreement at the FastMCP registration boundary: the versioned,
disk-frozen tool schema must describe exactly the tools and parameters the
live server actually registers. Parametrized over the live registry itself
(``contract.live_contract``), so a newly registered tool is covered without
a new test -- only a version bump and a regenerated schema file.
"""
from api.mcp_server import contract, server


def test_v41_schema_matches_the_live_fastmcp_registry():
    assert contract.TOOL_SCHEMA_VERSION == 41
    expected = contract.load_contract()
    live = contract.live_contract(server.mcp)
    assert live == expected
