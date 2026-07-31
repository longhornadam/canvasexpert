"""Create output folder structures for finished quizzes."""

from pathlib import Path
from typing import Optional

from engine.utils.text_utils import safe_filename_component


def sanitize_filename(title: str) -> str:
    """Convert a quiz title to a safe filename.

    Delegates to the shared ``safe_filename_component`` so Printables/Canvas
    Uploads names use the same convention (spaces preserved, illegal chars
    replaced, reserved device names guarded) as the rest of the
    teacher-visible workspace.

    Args:
        title: Raw quiz title

    Returns:
        Sanitized string safe for use in filenames
    """
    return safe_filename_component(title, fallback="")


def create_quiz_folder(output_dir: Path, quiz_title: str) -> Path:
    """Create folder for quiz outputs.

    Args:
        output_dir: Base output directory (Printables or Canvas Uploads)
        quiz_title: Quiz title (used for folder name)

    Returns:
        Path to created folder
    """
    safe_title = sanitize_filename(quiz_title) or "Untitled_Quiz"

    folder = output_dir / safe_title
    folder.mkdir(parents=True, exist_ok=True)

    return folder


def write_file(folder: Path, filename: str, content: bytes) -> Path:
    """Write bytes to file in folder.
    
    Args:
        folder: Folder path
        filename: File name
        content: File content as bytes
        
    Returns:
        Path to written file
    """
    filepath = folder / filename
    filepath.write_bytes(content)
    return filepath