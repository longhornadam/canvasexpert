from __future__ import annotations

from api.webui import workspace
from tools import design_theme_studio


def test_build_prunes_stale_cards_but_leaves_other_files(tmp_path, monkeypatch):
    """A theme that gets renamed or deleted must not leave its old card behind:
    a `yours-*.html` glob pushed to the design project would otherwise
    re-upload content that was supposed to be gone. build() should end with
    the output folder holding exactly what it just wrote, plus whatever else
    was already in there that isn't one of its own cards."""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    stale = out_dir / "yours-gone.html"
    stale.write_text("<article>a theme that no longer exists</article>",
                     encoding="utf-8")
    unrelated = out_dir / "notes.txt"
    unrelated.write_text("not a card, leave me alone", encoding="utf-8")

    monkeypatch.setattr(design_theme_studio, "OUT_DIR", out_dir)
    # An empty, non-existent workspace: no custom themes to build cards for,
    # so the only *.html this run writes are format.html, the built-ins, and
    # the starter card.
    monkeypatch.setattr(workspace, "workspace_root",
                        lambda: str(tmp_path / "workspace"))

    result = design_theme_studio.build()

    assert result == 0
    assert not stale.exists(), "a stale card must be pruned on rebuild"
    assert unrelated.exists(), "pruning must only ever touch *.html at the top level"
    assert (out_dir / "format.html").exists()
    assert (out_dir / "starter.html").exists()
