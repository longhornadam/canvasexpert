"""PowerGrader backend package.

Submodules are intentionally loaded lazily.  Feedback artifact code shares the
attachment router with this package, and eager imports here would create a
feedback-pipeline/OpenRouter circular import during offline tests.
"""
