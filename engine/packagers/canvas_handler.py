"""Canvas QTI 1.2 handler.

Converts validated Quiz objects into Canvas-compliant QTI ZIP packages.
Performs NO validation - trusts input is perfect.
"""

from pathlib import Path
from typing import Dict
from engine.core.quiz import Quiz
from engine.packaging.folder_creator import sanitize_filename
from engine.rendering.canvas.qti_builder import build_assessment_xml
from engine.rendering.canvas.qti_roundtrip import verify_qti_round_trip
from engine.rendering.canvas.manifest_builder import build_manifest_xml
from engine.rendering.canvas.metadata_builder import build_assessment_meta_xml
from engine.rendering.canvas.zip_packager import create_zip_bytes


class CanvasHandler:
    """Generate Canvas QTI 1.2 packages."""
    
    def package(self, quiz: Quiz, output_base: str) -> Dict[str, str]:
        """Create QTI ZIP package from quiz and write to file.
        
        Args:
            quiz: Validated Quiz object
            output_base: Base path for output files
            
        Returns:
            Dict with 'qti_path' and 'log_path'
        """
        import uuid
        guid = str(uuid.uuid4())

        assessment_xml = build_assessment_xml(quiz)
        verify_qti_round_trip(quiz, assessment_xml)
        manifest_xml = build_manifest_xml(quiz.title, guid)
        meta_xml = build_assessment_meta_xml(quiz.title, quiz.total_points(), guid, quiz.instructions)
        zip_bytes = create_zip_bytes(manifest_xml, assessment_xml, meta_xml, guid)

        # Write to file with explicit QTI suffix so users can spot the Canvas import package
        output_path = Path(output_base) / f"{sanitize_filename(quiz.title)}_QTI.zip"
        output_path.write_bytes(zip_bytes)
        
        # For now, no log_path, perhaps later
        return {
            'qti_path': str(output_path),
            'log_path': ''  # placeholder
        }
