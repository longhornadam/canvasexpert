"""Writing Record is a private evidence store, not an evaluator.

It stores only scrubbed student text and structural attribution after a
teacher-triggered acquisition. Canvas identifiers remain private at rest;
outbound data is rebuilt from an allowlist and safety-scanned. It never scores,
coaches, grades, or writes to Canvas.
"""
