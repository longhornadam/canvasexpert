"""The shape of a school day, kept separate from anything that displays it.

`models` is the vocabulary, `validate` checks a loaded schedule, `resolver`
answers "where are we right now" for an instant handed in by the caller, and
`calendar` is the one thin seam onto the existing academic calendar. Nothing
here reads the clock, and nothing here imports Glass: the question of which
section is in the room is useful well beyond a projector.

Import the submodules directly. This package deliberately re-exports nothing,
so importing it stays cheap in a bare context.
"""
