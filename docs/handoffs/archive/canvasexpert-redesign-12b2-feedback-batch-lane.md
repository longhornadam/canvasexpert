# Toyota handoff 12b2: guided and OpenRouter batch lane

Implement the accepted matrix rows for guided batch scoring, Copilot/manual batches, and
OpenRouter execution inside PowerGrader. Reuse existing SAFE packet generation, exact
three-file Copilot batch contract, pricing/budget checks, model settings, and import lane.
No external request in tests/rendering. Preserve fresh-chat-per-batch wording and honest
SAFE language. Test artifact equivalence, batch isolation, budgets/timeouts/provider
redaction, and import handoff. One commit; stop if data classification or provider payload
differs from legacy without Ferrari approval.
