"""File system utilities shared across modules."""

from pathlib import Path
from typing import List


def scan_directory(path: Path, pattern: str = "*.txt") -> List[Path]:
    """Scan directory for files matching pattern.
    
    Args:
        path: Directory to scan
        pattern: Glob pattern for matching files
        
    Returns:
        List of matching file paths
    """
    return list(path.glob(pattern))


def safe_filename(text: str) -> str:
    """Convert text to safe filename (remove special characters).
    
    Args:
        text: Text to convert
        
    Returns:
        Safe filename string
    """
    # TODO: Implement
    return text.replace(" ", "_")
