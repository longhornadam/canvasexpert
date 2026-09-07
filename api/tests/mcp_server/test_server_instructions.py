"""Guards on the always-loaded MCP surface: the instruction block and the
weight of the tool listing.

The listing and instruction block are delivered to connected clients, so their
serialized wire size is measured. Client and model token treatment varies. The
instruction block has been observed truncating mid-sentence in a real client,
so its ordering matters: routing and write rules come before discovery hints,
because the tail is what gets cut.
"""
import asyncio
import json

from api.mcp_server import server


# Observed truncation in a real client landed near 2,300 characters. We cannot
# hold every client to that, but we can stop the block growing: any addition
# now has to earn its place by displacing something.
INSTRUCTION_BUDGET = 3000
LISTING_BUDGET = 23000


def test_instruction_block_stays_within_budget():
    length = len(server._SERVER_INSTRUCTIONS)

    assert length <= INSTRUCTION_BUDGET, (
        f"server instructions are {length} chars, over the {INSTRUCTION_BUDGET} "
        "budget; trim something rather than raising the cap"
    )


def test_scoring_routes_through_powergrader_staging_by_default():
    """Staging is the default landing place for AI-scored work.

    Pushing to Canvas from the chat stays available, but the queue is where
    scored work belongs unless the teacher asks otherwise, and stage_scores is
    upstream of the New Quiz write either way.
    """
    instructions = server._SERVER_INSTRUCTIONS

    assert "stage_scores" in instructions
    assert "PowerGrader queue is where scored work belongs by default" in instructions
    assert "staged scores never reach Canvas on their own" in instructions
    assert "Staging is also the way in to the New Quiz write" in instructions


def test_chat_side_canvas_landing_is_still_offered():
    instructions = server._SERVER_INSTRUCTIONS

    assert "preview_new_quiz_scores" in instructions
    assert "apply_new_quiz_scores" in instructions
    assert "wants a New Quiz landed from the chat, do it" in instructions
    # The teacher's ask is the authorization, not a request for permission.
    assert "asking again" in instructions


def test_write_rules_precede_the_discovery_hints():
    """If a client truncates the tail, lose the product-guide nudge, not the
    rule that bounds how far one teacher request reaches."""
    instructions = server._SERVER_INSTRUCTIONS

    assert (instructions.index("does not carry to another assignment")
            < instructions.index("get_product_guide"))


def test_no_generated_schema_titles_reach_the_client():
    """pydantic labels every property with a title made from its own name, and
    every tool with <name>Arguments / <name>Outputs. It is 22% of the listing
    and says nothing the property key did not. Asserted on the real list_tools
    payload, not on our own copy of the schemas."""
    listed = asyncio.run(server.mcp.list_tools())
    wire = json.dumps([tool.model_dump(exclude_none=True) for tool in listed],
                      separators=(",", ":"), ensure_ascii=False)

    assert server._STRIPPED_SCHEMA_TITLES > 0, "the strip pass found nothing to strip"
    assert '"title"' not in wire, "a generated schema title is reaching clients again"
    assert len(wire) <= LISTING_BUDGET, (
        f"serialized tools/list is {len(wire)} chars, over the {LISTING_BUDGET} "
        "character budget"
    )


def test_the_schemas_themselves_survive_the_strip():
    """Stripping titles must not cost a name, a type, a default, or a required
    list: those are the parts a client needs to call the tool correctly."""
    listed = asyncio.run(server.mcp.list_tools())
    submissions = next(tool for tool in listed if tool.name == "get_submissions")
    schema = submissions.inputSchema

    assert schema["required"] == ["course_id", "assignment_id"]
    assert schema["properties"]["course_id"] == {"type": "string"}
    assert schema["properties"]["max_text_chars"] == {"default": 2000, "type": "integer"}
    assert schema["properties"]["include_text"]["default"] is True


def test_all_registered_tools_use_text_only_result_transport():
    listed = asyncio.run(server.mcp.list_tools())
    assert len(listed) == 50
    registry = server.mcp._tool_manager._tools
    assert all(tool.outputSchema is None for tool in listed)
    assert all(item.fn_metadata.output_schema is None
               for item in registry.values())


def test_protocol_call_returns_one_text_block_without_structured_result():
    result = asyncio.run(server.mcp.call_tool(
        "get_product_guide", {"topic": "overview"}))
    assert len(result) == 1
    assert result[0].type == "text"
    assert isinstance(result[0].text, str)


def test_compact_preserves_unicode_tables_and_runs_final_gate(monkeypatch):
    seen = []

    def gate(payload):
        seen.append(payload)
        return {"ok": False, "error": "échec", "table": {
            "columns": ["élève"], "rows": [["Zoë"]],
        }}

    monkeypatch.setattr(server.tools, "final_response_gate", gate)
    wire = server._compact({"raw": "discarded"})

    assert seen == [{"raw": "discarded"}]
    assert "échec" in wire and "Zoë" in wire
    assert "\\u00e9" not in wire
    assert json.loads(wire)["table"]["rows"] == [["Zoë"]]


def test_each_registered_wrapper_returns_one_gated_text_block(_synthetic_mcp):
    async def call_all():
        results = []
        for name in _synthetic_mcp["names"]:
            results.append((name, await server.mcp.call_tool(
                name, _synthetic_mcp["required_arguments"](name))))
        return results

    results = asyncio.run(call_all())
    assert len(results) == 50
    assert len(_synthetic_mcp["calls"]) == 50
    assert len(_synthetic_mcp["gated"]) == 50
    for name, content in results:
        assert len(content) == 1
        assert content[0].type == "text"
        assert json.loads(content[0].text) == {
            "ok": True,
            "delegate": name,
            "table": {"columns": ["élève"], "rows": [["Zoë"]]},
        }


def test_wrapper_protocol_preserves_structured_failure(_synthetic_mcp, monkeypatch):
    def refused(*args, **kwargs):
        return {"ok": False, "error": "synthetic refusal"}

    monkeypatch.setattr(server.tools, "list_courses", refused)
    content = asyncio.run(server.mcp.call_tool("list_courses", {}))
    assert len(content) == 1
    assert json.loads(content[0].text) == {
        "ok": False,
        "delegate": None,
        "table": {"columns": ["élève"], "rows": [["Zoë"]]},
    }
