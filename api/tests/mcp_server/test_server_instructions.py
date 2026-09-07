"""Guards on the always-loaded MCP surface: the instruction block and the
weight of the tool listing.

Both are paid for on every request to every connected client. The instruction
block has been observed truncating mid-sentence in a real client, so its
length is a real cost and its ordering matters: routing and write rules come
before the discovery hints, because the tail is what gets cut.
"""
import asyncio
import json

from api.mcp_server import server


# Observed truncation in a real client landed near 2,300 characters. We cannot
# hold every client to that, but we can stop the block growing: any addition
# now has to earn its place by displacing something.
INSTRUCTION_BUDGET = 3000


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
    assert "land a New Quiz from the chat" in instructions


def test_write_rules_precede_the_discovery_hints():
    """If a client truncates the tail, lose the product-guide nudge, not the
    rule that says to wait for the teacher before applying."""
    instructions = server._SERVER_INSTRUCTIONS

    assert instructions.index("wait for the teacher") < instructions.index("get_product_guide")


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
