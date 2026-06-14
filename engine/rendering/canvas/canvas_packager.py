"""Canvas QTI 1.2 packager.

Converts validated Quiz objects into Canvas-compliant QTI ZIP packages.
Performs NO validation - trusts input is perfect.
"""

from typing import Tuple
from engine.core.quiz import Quiz
from .qti_builder import build_assessment_xml
from .qti_roundtrip import verify_qti_round_trip
from .manifest_builder import build_manifest_xml
from .metadata_builder import build_assessment_meta_xml
from .zip_packager import create_zip_bytes


class CanvasPackager:
    """Generate Canvas QTI 1.2 packages."""
    
    def package(self, quiz: Quiz) -> Tuple[bytes, str]:
        """Create QTI ZIP package from quiz.
        
        Args:
            quiz: Validated Quiz object
            
        Returns:
            Tuple of (zip_bytes, guid)
        """
        import uuid
        guid = str(uuid.uuid4())

        assessment_xml = build_assessment_xml(quiz)
        verify_qti_round_trip(quiz, assessment_xml)
        manifest_xml = build_manifest_xml(quiz.title, guid)
        meta_xml = build_assessment_meta_xml(quiz.title, quiz.total_points(), guid, quiz.instructions)
        zip_bytes = create_zip_bytes(manifest_xml, assessment_xml, meta_xml, guid)
        return zip_bytes, guid
