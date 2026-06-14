
from __future__ import annotations
"""Answer specification models.

Complex answer types (especially numerical) get their own models
to keep question definitions clean.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional


@dataclass
class NumericalAnswer:
    """Scoring specification for numerical questions.
    
    Supports multiple tolerance modes:
    - exact: No tolerance (answer must match exactly)
    - percent_margin: Answer ± X% (e.g., 100 ± 5% = 95-105)
    - absolute_margin: Answer ± X (e.g., 100 ± 5 = 95-105)
    - range: Accept any value in [min, max]
    - significant_digits: Round to N sig figs (e.g., 3 sig figs: 123.456 → 123)
    - decimal_places: Round to N decimal places (e.g., 2 places: 123.456 → 123.46)
    
    Attributes:
        answer: The correct numerical answer
        tolerance_mode: One of the supported tolerance modes
        margin_value: For percent_margin or absolute_margin modes
        range_min: For range mode (minimum value)
        range_max: For range mode (maximum value)
        precision_value: For significant_digits or decimal_places modes
        lower_bound: Computed lower bound (set by validator)
        upper_bound: Computed upper bound (set by validator)
        strict_lower: If True, lower bound is exclusive (>) not inclusive (>=)
    """
    
    answer: Optional[Decimal] = None
    tolerance_mode: str = "exact"
    margin_value: Optional[Decimal] = None
    range_min: Optional[Decimal] = None
    range_max: Optional[Decimal] = None
    precision_value: Optional[int] = None
    lower_bound: Optional[Decimal] = None
    upper_bound: Optional[Decimal] = None
    strict_lower: bool = False
    
    def validate(self) -> List[str]:
        """Validate the answer specification for internal consistency.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors: List[str] = []
        mode = self.tolerance_mode
        
        # Check answer is present for non-range modes
        if mode != "range" and self.answer is None:
            errors.append("Numerical question requires answer; provide a numeric 'answer' field for this item.")
        
        # Validate percent_margin mode
        if mode == "percent_margin":
            if self.margin_value is None:
                errors.append("Percent margin requires tolerance value; set 'margin_value' to the allowed percent wiggle room (e.g., 5 for ±5%).")
            elif self.margin_value < 0:
                errors.append("Percent margin must be non-negative; use zero or a positive percent tolerance.")
        
        # Validate absolute_margin mode
        elif mode == "absolute_margin":
            if self.margin_value is None:
                errors.append("Absolute margin requires tolerance value; set 'margin_value' to the allowed numeric wiggle room (e.g., 2 for ±2).")
            elif self.margin_value < 0:
                errors.append("Absolute margin must be non-negative; use zero or a positive tolerance.")
        
        # Validate significant_digits mode
        elif mode == "significant_digits":
            if self.precision_value is None:
                errors.append("Significant digits mode requires precision value; set 'precision_value' to how many significant digits are graded.")
            elif self.precision_value < 0:
                errors.append("Precision must be non-negative; use a zero or positive integer for significant digits.")
        
        # Validate decimal_places mode
        elif mode == "decimal_places":
            if self.precision_value is None:
                errors.append("Decimal places mode requires precision value; set 'precision_value' to how many decimal places are graded.")
            elif self.precision_value < 0:
                errors.append("Precision must be non-negative; use a zero or positive integer for decimal places.")
        
        # Validate range mode
        elif mode == "range":
            if self.range_min is None or self.range_max is None:
                errors.append("Range mode requires both minimum and maximum values; provide 'range_min' and 'range_max'.")
            elif self.range_min >= self.range_max:
                errors.append("Range minimum must be less than maximum; swap or adjust the values so min < max.")
        
        # Check bounds are present and valid
        if self.lower_bound is None or self.upper_bound is None:
            errors.append("Computed bounds missing for numerical question; ensure bounds are calculated from the answer/tolerance settings.")
        elif self.lower_bound > self.upper_bound:
            errors.append("Lower bound cannot exceed upper bound; check tolerance/range settings so lower <= upper.")
        
        return errors
