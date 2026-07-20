"""Main validation orchestrator.

Coordinates all validation rules and auto-fixers.
Returns validation status + cleaned quiz + fix log.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from enum import Enum

from ..core.quiz import Quiz
from .rules import structure_rules, fairness_rules
from .fixers import auto_fixer


class ValidationStatus(Enum):
    """Validation outcome."""
    PASS = "PASS"              # No issues detected
    WEAK_PASS = "WEAK_PASS"    # Fairness warnings but structurally valid
    FAIL = "FAIL"              # Critical errors that cannot be fixed


@dataclass
class ValidationResult:
    """Result of validation process.
    
    Attributes:
        status: Overall validation outcome
        quiz: Quiz object (possibly modified by auto-fixers)
        fix_log: List of auto-fixes that were applied
        errors: List of errors (populated for FAIL status)
        warnings: List of warnings (populated for WEAK_PASS)
    """
    status: ValidationStatus
    quiz: Quiz
    fix_log: List[str]
    errors: List[str]
    warnings: List[str]


class QuizValidator:
    """Validate and auto-fix quiz content."""
    
    def __init__(self):
        """Initialize validator."""
        self.fixer = auto_fixer.AutoFixer()
    
    def validate(self, quiz: Quiz) -> ValidationResult:
        """Run all validation rules and auto-fixers.
        
        Workflow:
        1. Check structure (hard fails - cannot auto-fix)
        2. If structure valid, apply auto-fixes
        3. Check fairness (soft fails - warnings only)
        4. Return result with status + logs
        
        Args:
            quiz: Unvalidated Quiz object from parser
            
        Returns:
            ValidationResult with status, cleaned quiz, and logs
        """
        fix_log: List[str] = []
        errors: List[str] = []
        warnings: List[str] = []
        
        # Step 1: Check structure (hard fails)
        structure_errors = structure_rules.validate_structure(quiz)
        if structure_errors:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                quiz=quiz,
                fix_log=[],
                errors=structure_errors,
                warnings=[]
            )
        
        # Step 2: Apply auto-fixes
        quiz, fix_messages = self.fixer.fix_all(quiz)
        fix_log.extend(fix_messages)

        # Step 2b: Length-bias check (hard fail so LLM/author can fix wording)
        length_bias_errors = fairness_rules.check_length_bias(quiz)
        if length_bias_errors:
            return ValidationResult(
                status=ValidationStatus.FAIL,
                quiz=quiz,
                fix_log=fix_log,
                errors=length_bias_errors,
                warnings=[]
            )
        
        # Step 3: Check fairness (soft fails)
        fairness_warnings = fairness_rules.check_fairness(quiz)
        warnings.extend(fairness_warnings)
        
        # Step 4: Determine final status
        if warnings:
            status = ValidationStatus.WEAK_PASS
        else:
            status = ValidationStatus.PASS
        
        return ValidationResult(
            status=status,
            quiz=quiz,
            fix_log=fix_log,
            errors=[],
            warnings=warnings
        )
