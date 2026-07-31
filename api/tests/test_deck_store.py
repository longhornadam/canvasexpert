"""Tests for SmartDeck storage (deck_store.py)."""
import json
import os
import pytest
from pathlib import Path
from api.webui import deck_store, sf, workspace


@pytest.fixture
def mock_workspace(monkeypatch, tmp_path):
    """Mock workspace to use tmp_path for testing."""
    # Create the directory structure
    decks_dir = tmp_path / "Library" / "SmartDecks" / "Decks"
    decks_dir.mkdir(parents=True, exist_ok=True)

    system_dir = tmp_path / "_System" / "Archive" / "SmartDecks"
    system_dir.mkdir(parents=True, exist_ok=True)

    # Mock workspace.library_folder to return our test directory
    def mock_library_folder(name, root=None):
        if name == "SmartDecks":
            return str(tmp_path / "Library" / "SmartDecks")
        return str(tmp_path / "Library" / name) if name else str(tmp_path / "Library")

    def mock_system_folder(name=None, root=None):
        if name:
            return str(tmp_path / "_System" / name)
        return str(tmp_path / "_System")

    def mock_path_within_workspace(path, root=None):
        try:
            resolved = os.path.realpath(path)
            workspace_root = os.path.realpath(str(tmp_path))
            return os.path.commonpath([resolved, workspace_root]) == workspace_root
        except ValueError:
            return False

    monkeypatch.setattr(workspace, "library_folder", mock_library_folder)
    monkeypatch.setattr(workspace, "system_folder", mock_system_folder)
    monkeypatch.setattr(workspace, "path_within_workspace", mock_path_within_workspace)
    # Also monkeypatch deck_store's references to these functions
    monkeypatch.setattr(deck_store.workspace, "library_folder", mock_library_folder)
    monkeypatch.setattr(deck_store.workspace, "system_folder", mock_system_folder)
    monkeypatch.setattr(deck_store.workspace, "path_within_workspace", mock_path_within_workspace)

    return tmp_path


class TestPathJailing:
    """Test path traversal defense."""

    def test_save_deck_rejects_traversal_in_date(self, mock_workspace):
        """Deck with traversal in date field should be rejected."""
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "../../../evil",
            "title": "Bad Deck",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, problems = deck_store.save_deck(data)
        # Validation should fail because date doesn't match YYYY-MM-DD format
        assert result is None
        assert len(problems) > 0

    def test_load_deck_rejects_traversal(self, mock_workspace):
        """load_deck with traversal in deck_id should be rejected."""
        result, problems = deck_store.load_deck("../../../evil")
        assert result is None
        assert any("traversal" in p.lower() for p in problems)

    def test_archive_deck_rejects_traversal(self, mock_workspace):
        """archive_deck with traversal in deck_id should be rejected."""
        success, problems = deck_store.archive_deck("../../../evil")
        assert success is False
        assert any("traversal" in p.lower() for p in problems)

    def test_delete_deck_rejects_traversal(self, mock_workspace):
        """delete_deck with traversal in deck_id should be rejected."""
        success, problems = deck_store.delete_deck("../../../evil")
        assert success is False
        assert any("traversal" in p.lower() for p in problems)

    def test_delete_deck_rejects_absolute_path(self, mock_workspace):
        """delete_deck with absolute path should be rejected."""
        success, problems = deck_store.delete_deck("C:\\Windows\\System32\\evil")
        assert success is False
        # Should be rejected due to path jailing
        assert len(problems) > 0

    def test_load_deck_rejects_unc_path(self, mock_workspace):
        """load_deck with UNC path should be rejected."""
        result, problems = deck_store.load_deck("\\\\server\\share\\evil")
        assert result is None
        assert len(problems) > 0


class TestDeckRevisions:
    """Test revision numbering and archiving."""

    def test_save_deck_first_revision_is_1(self, mock_workspace):
        """First save of a date should get revision 1."""
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "First Deck",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, problems = deck_store.save_deck(data)
        assert result is not None
        assert result["revision"] == 1
        assert result["deck_id"] == "2026-08-14.r1"

    def test_save_deck_increments_revision(self, mock_workspace):
        """Second save of the same date should increment revision."""
        data1 = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "First Version",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result1, _ = deck_store.save_deck(data1)
        assert result1["revision"] == 1

        data2 = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Second Version",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "B"}],
        }
        result2, _ = deck_store.save_deck(data2)
        assert result2["revision"] == 2

    def test_save_deck_archives_prior_revision(self, mock_workspace):
        """Saving a new revision should move the old one to Archived."""
        decks_dir = mock_workspace / "Library" / "SmartDecks" / "Decks"
        archived_dir = decks_dir / "Archived"

        data1 = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "First",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result1, _ = deck_store.save_deck(data1)

        # First revision should be active
        assert (decks_dir / f"{result1['deck_id']}.json").exists()
        assert not archived_dir.exists() or not (archived_dir / f"{result1['deck_id']}.json").exists()

        data2 = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Second",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "B"}],
        }
        result2, _ = deck_store.save_deck(data2)

        # First revision should be archived now
        assert not (decks_dir / f"{result1['deck_id']}.json").exists()
        assert (archived_dir / f"{result1['deck_id']}.json").exists()
        # Second revision should be active
        assert (decks_dir / f"{result2['deck_id']}.json").exists()


class TestValidationInSaveDeck:
    """Test that save_deck validates before writing."""

    def test_save_deck_with_invalid_data_writes_nothing(self, mock_workspace):
        """save_deck with validation errors should write no files."""
        decks_dir = mock_workspace / "Library" / "SmartDecks" / "Decks"

        # Data missing required fields
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Bad",
            # Missing slides
        }
        result, problems = deck_store.save_deck(data)
        assert result is None
        assert len(problems) > 0
        # No files should be created
        assert not list(decks_dir.glob("*.json"))


class TestListDecks:
    """Test deck listing."""

    def test_list_active_decks_empty(self, mock_workspace):
        """list_decks should return empty list when no decks exist."""
        decks = deck_store.list_decks("active")
        assert decks == []

    def test_list_active_decks_after_save(self, mock_workspace):
        """list_decks should show saved decks."""
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test Deck",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, _ = deck_store.save_deck(data)

        decks = deck_store.list_decks("active")
        assert len(decks) == 1
        assert decks[0]["deck_id"] == result["deck_id"]
        assert decks[0]["title"] == "Test Deck"
        assert decks[0]["date"] == "2026-08-14"
        assert decks[0]["revision"] == 1

    def test_list_archived_decks(self, mock_workspace):
        """list_decks should list archived decks separately."""
        # Create and then archive a deck
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test Deck",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, _ = deck_store.save_deck(data)
        deck_id = result["deck_id"]

        # Archive it
        deck_store.archive_deck(deck_id)

        # Should not be in active list
        active = deck_store.list_decks("active")
        assert len(active) == 0

        # Should be in archived list
        archived = deck_store.list_decks("archived")
        assert len(archived) == 1
        assert archived[0]["deck_id"] == deck_id


class TestLoadDeck:
    """Test loading saved decks."""

    def test_load_deck_from_active(self, mock_workspace):
        """load_deck should read from active directory."""
        original_data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test Deck",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "Hello"}],
        }
        result, _ = deck_store.save_deck(original_data)

        loaded_data, problems = deck_store.load_deck(result["deck_id"])
        assert loaded_data is not None
        assert loaded_data["title"] == "Test Deck"
        assert loaded_data["slides"][0]["title"] == "Hello"

    def test_load_deck_from_archived(self, mock_workspace):
        """load_deck should find decks in archived directory."""
        original_data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Archived Deck",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "Old"}],
        }
        result, _ = deck_store.save_deck(original_data)
        deck_id = result["deck_id"]

        # Archive it
        deck_store.archive_deck(deck_id)

        # Should still be loadable
        loaded_data, problems = deck_store.load_deck(deck_id)
        assert loaded_data is not None
        assert loaded_data["title"] == "Archived Deck"

    def test_load_nonexistent_deck(self, mock_workspace):
        """load_deck should return error for nonexistent deck."""
        loaded_data, problems = deck_store.load_deck("2026-08-14.r999")
        assert loaded_data is None
        assert len(problems) > 0
        assert "not found" in problems[0]


class TestArchiveDeck:
    """Test archiving decks."""

    def test_archive_active_deck(self, mock_workspace):
        """archive_deck should move active deck to archived."""
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, _ = deck_store.save_deck(data)
        deck_id = result["deck_id"]

        decks_dir = mock_workspace / "Library" / "SmartDecks" / "Decks"
        archived_dir = decks_dir / "Archived"

        # Verify it's active before archiving
        assert (decks_dir / f"{deck_id}.json").exists()

        # Archive it
        success, problems = deck_store.archive_deck(deck_id)
        assert success is True

        # Verify it's archived now
        assert not (decks_dir / f"{deck_id}.json").exists()
        assert (archived_dir / f"{deck_id}.json").exists()

    def test_archive_nonexistent_deck(self, mock_workspace):
        """archive_deck should fail for nonexistent deck."""
        success, problems = deck_store.archive_deck("2026-08-14.r999")
        assert success is False
        assert "not found" in problems[0]


class TestDeleteDeck:
    """Test deleting decks."""

    def test_delete_active_deck(self, mock_workspace):
        """delete_deck should move deck to Archive."""
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, _ = deck_store.save_deck(data)
        deck_id = result["deck_id"]

        decks_dir = mock_workspace / "Library" / "SmartDecks" / "Decks"
        archive_dir = mock_workspace / "_System" / "Archive" / "SmartDecks"

        # Verify it's active
        assert (decks_dir / f"{deck_id}.json").exists()

        # Delete it
        success, problems = deck_store.delete_deck(deck_id)
        assert success is True

        # Verify it's gone from active and in archive
        assert not (decks_dir / f"{deck_id}.json").exists()
        assert (archive_dir / f"{deck_id}.json").exists()

    def test_delete_archived_deck(self, mock_workspace):
        """delete_deck should delete from archived directory too."""
        data = {
            "version": "1.0-json",
            "type": "DECK",
            "date": "2026-08-14",
            "title": "Test",
            "slides": [{"id": "s1", "block": "1st", "layout": "title_body", "title": "A"}],
        }
        result, _ = deck_store.save_deck(data)
        deck_id = result["deck_id"]

        # Archive it first
        deck_store.archive_deck(deck_id)

        decks_dir = mock_workspace / "Library" / "SmartDecks" / "Decks"
        archive_dir = mock_workspace / "_System" / "Archive" / "SmartDecks"

        # Verify it's in archived
        assert (decks_dir / "Archived" / f"{deck_id}.json").exists()

        # Delete it
        success, problems = deck_store.delete_deck(deck_id)
        assert success is True

        # Verify it's gone from archived and in system archive
        assert not (decks_dir / "Archived" / f"{deck_id}.json").exists()
        assert (archive_dir / f"{deck_id}.json").exists()

    def test_delete_nonexistent_deck(self, mock_workspace):
        """delete_deck should fail for nonexistent deck."""
        success, problems = deck_store.delete_deck("2026-08-14.r999")
        assert success is False
        assert "not found" in problems[0]


class TestRevisionUniqueness:
    """Revision numbers must be unique per date across every folder a deck lives in.

    Scanning only the active folder restarted numbering at r1 once a date's decks
    had been archived or deleted, so the next archive moved a fresh r1 on top of
    the stored one and destroyed it.
    """

    def _deck(self, title, date="2026-08-14"):
        return {
            "version": "1.0-json",
            "type": "DECK",
            "date": date,
            "title": title,
            "slides": [{"id": "s1", "block": "1st", "layout": "title_only", "title": "A"}],
        }

    def test_revision_does_not_restart_after_archive(self, mock_workspace):
        """A save after archiving must not reuse the archived revision number."""
        first, problems = deck_store.save_deck(self._deck("ORIGINAL"))
        assert problems == []
        assert first["deck_id"] == "2026-08-14.r1"

        success, problems = deck_store.archive_deck("2026-08-14.r1")
        assert success, problems

        second, problems = deck_store.save_deck(self._deck("REPLACEMENT"))
        assert problems == []
        assert second["deck_id"] == "2026-08-14.r2"

    def test_revision_does_not_restart_after_delete(self, mock_workspace):
        """Soft-deleted revisions also reserve their number."""
        first, problems = deck_store.save_deck(self._deck("ORIGINAL"))
        assert problems == []

        success, problems = deck_store.delete_deck(first["deck_id"])
        assert success, problems

        second, problems = deck_store.save_deck(self._deck("REPLACEMENT"))
        assert problems == []
        assert second["deck_id"] == "2026-08-14.r2"

    def test_archiving_twice_preserves_the_first_deck(self, mock_workspace):
        """The end-to-end case: archive, re-author, archive again. Both survive."""
        first, _ = deck_store.save_deck(self._deck("ORIGINAL"))
        deck_store.archive_deck(first["deck_id"])
        second, _ = deck_store.save_deck(self._deck("REPLACEMENT"))
        success, problems = deck_store.archive_deck(second["deck_id"])
        assert success, problems

        archived = {d["deck_id"]: d["title"] for d in deck_store.list_decks("archived")}
        assert archived == {"2026-08-14.r1": "ORIGINAL", "2026-08-14.r2": "REPLACEMENT"}

    def test_revision_numbering_is_per_date(self, mock_workspace):
        """A different date starts its own numbering at r1."""
        deck_store.save_deck(self._deck("A", date="2026-08-14"))
        deck_store.archive_deck("2026-08-14.r1")
        other, problems = deck_store.save_deck(self._deck("B", date="2026-08-15"))
        assert problems == []
        assert other["deck_id"] == "2026-08-15.r1"

    def test_archive_refuses_to_overwrite_an_occupied_destination(self, mock_workspace):
        """Legacy on-disk collisions must fail loudly, not clobber the stored deck."""
        first, _ = deck_store.save_deck(self._deck("ORIGINAL"))
        deck_store.archive_deck(first["deck_id"])

        # Simulate a colliding file written by the pre-fix numbering.
        decks_dir = mock_workspace / "Library" / "SmartDecks" / "Decks"
        (decks_dir / "2026-08-14.r1.json").write_text(
            json.dumps(self._deck("LEGACY COLLIDER")), encoding="utf-8")

        success, problems = deck_store.archive_deck("2026-08-14.r1")
        assert success is False
        assert "already stored" in problems[0]

        archived = decks_dir / "Archived" / "2026-08-14.r1.json"
        assert json.loads(archived.read_text(encoding="utf-8"))["title"] == "ORIGINAL"
        assert (decks_dir / "2026-08-14.r1.json").exists()
