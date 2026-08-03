#!/usr/bin/env python3
"""
Eduphoria Assessment Parser - LLM-Friendly Output
Converts XLSX assessment files into validated JSON format for reliable LLM interaction

This tool parses both STAAR and Benchmark assessment files from Eduphoria Aware
and converts them into structured JSON that LLMs cannot misinterpret or hallucinate about.
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

import openpyxl

from .tabular import is_blank, not_blank, read_csv, read_xlsx

if TYPE_CHECKING:  # identity imports the Vault, which would be a cycle at runtime
    from .identity import VaultIdentity


@dataclass
class StudentPerformance:
    """Individual student performance record.

    Only stores standards the student MISSED (score < 1.0) or had missing data (None).
    Standards mastered (score >= 1.0) are omitted for brevity.

    IMPORTANT: The score value for each missed standard is the PERCENT CORRECT (0.0-1.0),
    NOT percent missed. E.g., 0.5 means the student got 50% of questions correct for that standard.
    """
    student_name: str
    local_id: str
    special_ed: str
    emergent_bilingual: str
    ethnicity: str
    missed_standards: Dict[str, Optional[float]]  # Standard code -> PERCENT CORRECT (0.0-1.0) or None if missing
    raw_score: int
    percent_score: float
    scale_score: Optional[int]  # STAAR only
    approaches: str
    meets: str
    masters: str


@dataclass
class AssessmentSummary:
    """Summary statistics for the assessment"""
    total_students: int
    avg_raw_score: float
    avg_percent_score: float
    approaches_count: int
    approaches_percent: float
    meets_count: int
    meets_percent: float
    masters_count: int
    masters_percent: float
    avg_scale_score: Optional[float]  # STAAR only


@dataclass
class StandardAnalysis:
    """Analysis for individual standard"""
    standard_code: str
    canonical_code: str  # grade-agnostic code for cross-grade comparisons
    standard_type: str  # "Readiness" or "Supporting"
    avg_score: float
    proficiency_count: int  # Students scoring 1.0
    proficiency_rate: float
    total_students: int
    grade_7_staar_frequency: Optional[int] = None  # From frequency distribution


@dataclass
class AssessmentData:
    """Complete assessment data structure"""
    metadata: Dict
    students: List[StudentPerformance]
    summary: AssessmentSummary
    standard_analysis: List[StandardAnalysis]
    validation_report: Dict


# Load optional TEKS cross-grade overrides from a JSON file (key=original code, value=canonical code)
def _load_teks_crosswalk() -> Dict[str, str]:
    crosswalk_path = Path(__file__).parent / "teks_crosswalk.json"
    if not crosswalk_path.exists():
        return {}
    try:
        with open(crosswalk_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Expect a flat dict: {"6.2(B) [R]": "RLA.2(B) [R]", ...}
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


TEKS_CROSSWALK = _load_teks_crosswalk()


# Merged report-type label at Excel F2, lowercased/stripped -> internal breakdown type.
# This is the authoritative discriminator between the three known Eduphoria Aware
# exports. See detect_report_type() and pick_parser() below.
REPORT_TYPE_LABELS = {
    "all learning standards": "learning_standard",
    "all rcs": "reporting_category",
    "all responses": "item_response",
}


def detect_report_type(file_path: Path) -> Optional[str]:
    """Read the merged report-type label at Excel F2 (0-indexed row 1, column 5).

    Returns one of "learning_standard", "reporting_category", "item_response",
    or None when the label is missing, unrecognized, or the file cannot be
    read as an Excel file at all (any read error is swallowed).
    """
    try:
        preview = read_xlsx(file_path, header=None, nrows=3)
        val = preview.iloc[1, 5]
    except Exception:
        return None
    if is_blank(val):
        return None
    label = str(val).strip().lower()
    return REPORT_TYPE_LABELS.get(label)


def _data_start_row(file_path: Path, default: int) -> int:
    """Return the 0-indexed row where student data begins.

    Derived from the vertical merge on column A (e.g. Excel A2:A6), which
    Eduphoria uses to merge the student-name header cell down through every
    header sub-row. The merge's 1-indexed max_row is, conveniently, exactly
    equal to the 0-indexed index of the first data row (Excel row
    max_row+1 -> index max_row). Falls back to `default` when there is
    no such merge, the column A header isn't merged at all, or the file can't
    be opened (e.g. read_only quirks, corrupt file).
    """
    try:
        # NOT read_only=True: merged-cell ranges are unreliable to enumerate
        # in openpyxl's read-only mode.
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        for merged_range in ws.merged_cells.ranges:
            if merged_range.min_col == 1 and merged_range.min_row == 2:
                return merged_range.max_row
    except Exception:
        return default
    return default


def _clean_id(val) -> str:
    """Render a local-ID cell as a stable string.

    A single blank cell anywhere in an otherwise-integer ID column silently
    used to promote the whole column to float (e.g. 696969 -> 696969.0),
    which would change the anonymizer's map key across re-exports and
    re-pseudonymize the roster. Render integral floats without the trailing
    ".0"; NaN/None become "".
    """
    if val is None:
        return ""
    try:
        if is_blank(val):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val).strip()


def assert_no_leaks(text: str, anonymizer: Optional["VaultIdentity"], artifact: str) -> str:
    """Fail closed if a generated artifact still contains real identities.

    Applied to every artifact, not just the JSON. The teacher report lists
    student names under each missed standard and the parent narratives are one
    block per student, so both carry more identity surface than the JSON that
    was previously the only checked output.
    """
    if anonymizer is None:
        return text
    leaks = anonymizer.detect_leaks(text)
    if leaks:
        raise ValueError(
            f"Anonymization failed for {artifact}; found real identities: "
            f"{', '.join(sorted(set(leaks))[:5])}"
        )
    return text


class EducationDataParser:
    """Parser for Eduphoria Aware assessment files"""

    # Grade 7 STAAR frequency data (from your PDFs)
    GRADE_7_FREQUENCIES = {
        '7.2(A)': 2, '7.2(B)': 9, '7.2(C)': 2,
        '7.5(C)': 1, '7.5(E)': 23, '7.5(F)': 22, '7.5(G)': 5, '7.5(H)': 5,
        '7.7(A)': 6, '7.7(B)': 7, '7.7(C)': 1, '7.7(D)': 5,
        '7.8(C)': 5, '7.8(D.i)': 4, '7.8(D.ii)': 1, '7.8(D.iii)': 4,
        '7.8(E.i)': 3, '7.8(E.ii)': 3, '7.8(E.iii)': 3,
        '7.9(A)': 7, '7.9(B)': 4, '7.9(C)': 4, '7.9(D)': 6, '7.9(E)': 1, '7.9(F)': 7, '7.9(G)': 6,
        '7.6(B)': 1, '7.6(C)': 8, '7.6(D)': 9,
        '7.10(B)(i)': 14, '7.10(B)(ii)': 8, '7.10(C)': 19,
        '7.10(D)': 6, '7.10(D)(i)': 7, '7.10(D)(ii)': 1, '7.10(D)(iii)': 2,
        '7.10(D)(iv)': 2, '7.10(D)(v)': 1, '7.10(D)(vi)': 1, '7.10(D)(vii)': 5,
        '7.10(D)(viii)': 8, '7.10(D)(ix)': 9,
        '7.11(B)': 2, '7.11(C)': 1
    }

    def __init__(self, file_path: str, breakdown_type: str = "learning_standard"):
        self.file_path = Path(file_path)
        self.breakdown_type = breakdown_type
        self.raw_df = None
        self.validation_issues = []
        # Aggregated per-standard metrics, populated during student extraction
        self._standard_metrics: Dict[str, Dict[str, float]] = {}

    @staticmethod
    def looks_like_eduphoria(file_path: Path) -> bool:
        """Heuristic to detect Eduphoria layout to avoid false positives."""
        try:
            preview = read_xlsx(file_path, header=None, nrows=4)
        except Exception:
            return False
        if preview.shape[1] < 6 or preview.shape[0] < 3:
            return False
        cell = preview.iloc[0, 5]
        std_cell = preview.iloc[2, 5] if preview.shape[1] > 5 else None
        return not_blank(cell) or not_blank(std_cell)

    @staticmethod
    def _canonical_teks(code: str, breakdown_type: str = "learning_standard") -> str:
        """Return a grade-agnostic canonical code for cross-assessment comparisons.

        Reporting-category codes (e.g. "R1") are a different grain than TEKS
        learning standards and must never collide with a TEKS code in the
        cross-assessment rollup, so they get an "RC:" prefix instead of TEKS
        crosswalk/grade normalization.

        Known limitation (out of scope): "RC:R1" from a math export would
        still collide with "RC:R1" from an RLA export, since Eduphoria's RC
        codes aren't subject-qualified. Not fixed here.
        """
        if breakdown_type == "reporting_category":
            return f"RC:{str(code).strip()}"
        if code in TEKS_CROSSWALK:
            return TEKS_CROSSWALK[code]
        s = str(code).strip()
        m = re.match(r"^\d+\.(.+)$", s)
        if m:
            return m.group(1).strip()
        return s

    @staticmethod
    def _yn(val: str) -> str:
        """Normalize Yes/No-ish values to 'y' or 'n' for token efficiency."""
        s = (str(val) if val is not None else '').strip().lower()
        if s in {"yes", "y", "true", "t", "1"}:
            return 'y'
        if s in {"no", "n", "false", "f", "0"}:
            return 'n'
        return s or ''

    @staticmethod
    def _normalize_eb(val: str) -> str:
        """Normalize Emergent Bilingual status to compact codes.
        - 'y' = EB
        - '1st' = Monitored 1st Year
        - '2nd' = Monitored 2nd Year
        - 'fmr' = Former EB
        - 'n' = Not EB
        - otherwise a short lowercase token
        """
        s = (str(val) if val is not None else '').strip().lower()
        if not s or s in {"no", "n", "none", "non-eb", "not eb"}:
            return 'n'
        if "non-emergent" in s or "non emergent" in s:
            return 'n'
        if s in {"yes", "y", "eb", "emergent bilingual"}:
            return 'y'
        if "1" in s and "monitor" in s:
            return '1st'
        if ("2" in s and "monitor" in s) or ("second" in s and "monitor" in s):
            return '2nd'
        if "former" in s:
            return 'fmr'
        return s[:6]  # keep a short token if unknown

    def parse(self) -> AssessmentData:
        """Main parsing method - returns complete assessment data"""
        self._read_file()
        metadata = self._extract_metadata()
        students = self._extract_students(metadata)
        summary = self._calculate_summary(students)
        standard_analysis = self._analyze_standards(students, metadata['standards'])

        validation_report = {
            'file_parsed': str(self.file_path),
            'parse_timestamp': datetime.now().isoformat(),
            'validation_passed': len(self.validation_issues) == 0,
            'issues': self.validation_issues,
            'data_quality_checks': self._run_quality_checks(students, metadata)
        }

        return AssessmentData(
            metadata=metadata,
            students=students,
            summary=summary,
            standard_analysis=standard_analysis,
            validation_report=validation_report
        )

    def _read_file(self):
        """Read raw Excel file"""
        try:
            self.raw_df = read_xlsx(self.file_path, header=None)
        except Exception as e:
            raise ValueError(f"Failed to read file: {e}")

    def _extract_metadata(self) -> Dict:
        """Extract assessment metadata from headers"""
        # Row 0, Column 5: Assessment name
        assessment_name = self.raw_df.iloc[0, 5]
        if is_blank(assessment_name):
            self.validation_issues.append("WARNING: Assessment name not found in expected location")
            assessment_name = "Unknown Assessment"

        # Parse filename
        filename = self.file_path.stem
        parts = filename.split('_')

        campus = parts[0] if len(parts) > 0 else "Unknown"
        # Prefer assessment_name content for type; fallback to filename
        name_str = str(assessment_name) if assessment_name is not None else ""
        fname = self.file_path.name
        if "STAAR" in name_str.upper() or "STAAR" in fname.upper():
            assessment_type = "STAAR"
        elif "BENCHMARK" in name_str.upper() or "BENCHMARK" in fname.upper():
            assessment_type = "BENCHMARK"
        else:
            assessment_type = "BENCHMARK"

        # Extract grade
        grade = None
        for part in parts:
            if part.isdigit() and len(part) == 1:
                grade = part
                break
        if not grade:
            # Try to parse grade from assessment name (e.g., "Gr 6", "Grade 6", "RLA 6")
            s = name_str
            m = re.search(r"\bGr(?:ade)?\s*(\d)\b", s, flags=re.IGNORECASE)
            if not m:
                m = re.search(r"\bRLA\s*(\d)\b", s, flags=re.IGNORECASE)
            if m:
                grade = m.group(1)
        if not grade:
            self.validation_issues.append("WARNING: Could not extract grade from filename or title")

        # Row 2: Extract standards
        standards = []
        standard_columns = []

        for col in range(5, len(self.raw_df.columns)):
            val = self.raw_df.iloc[2, col]
            if self.breakdown_type == "reporting_category":
                # RC codes (e.g. "R1") carry no bracket notation; any non-empty
                # stripped string in the code row counts as a reporting category.
                is_code = not_blank(val) and isinstance(val, str) and val.strip() != ""
            else:
                # Learning-standard codes look like "7.2(B) [R]".
                is_code = not_blank(val) and isinstance(val, str) and '[' in val
            if is_code:
                standards.append(val)
                standard_columns.append(col)
            elif is_blank(val) and len(standards) > 0:
                break

        if len(standards) == 0:
            raise ValueError(
                f"No standards found in {self.file_path.name} "
                f"(breakdown_type={self.breakdown_type}). The file layout does not "
                "match the expected Eduphoria report type."
            )

        # Classify standards
        readiness_standards = [s for s in standards if '[R]' in s]
        supporting_standards = [s for s in standards if '[S]' in s]
        canonical_standards = [self._canonical_teks(s, self.breakdown_type) for s in standards]

        # Attempt to detect optional summary columns after the standards using header row (row 1)
        summary_cols = {}
        header_row = 1
        start_after = (standard_columns[-1] + 1) if standard_columns else 5
        label_map = {
            'raw': ['raw score', 'raw'],
            'scale': ['scale score', 'scale'],
            'percent': ['percent score', 'percent', '%'],
            'approaches': ['approaches'],
            'meets': ['meets'],
            'masters': ['masters']
        }
        for col in range(start_after, len(self.raw_df.columns)):
            val = self.raw_df.iloc[header_row, col]
            if isinstance(val, str) and val.strip():
                low = val.strip().lower()
                for key, aliases in label_map.items():
                    if any(a in low for a in aliases):
                        summary_cols[key] = col
                        break

        return {
            'assessment_name': str(assessment_name),
            'filename': filename,
            'campus': campus,
            'grade': grade,
            'assessment_type': assessment_type,
            'num_standards': len(standards),
            'standards': standards,
            'standard_columns': standard_columns,
            'readiness_standards': readiness_standards,
            'supporting_standards': supporting_standards,
            'canonical_standards': canonical_standards,
            'summary_col_start': 5 + len(standards),
            'summary_columns': summary_cols,
            'breakdown_type': self.breakdown_type,
        }

    def _extract_students(self, metadata: Dict) -> List[StudentPerformance]:
        """Extract all student records using pre-extracted metadata (avoids duplicate warnings)."""
        students = []
        # prepare per-standard aggregation buckets
        self._standard_metrics = {
            std: {"sum": 0.0, "count": 0, "mastered": 0, "missing": 0}
            for std in metadata['standards']
        }

        # Student data start is derived from the vertical merge on column A
        # (defaults to row 3, the pre-fix hardcoded value, when undetectable).
        data_start = _data_start_row(self.file_path, default=3)
        for row_idx in range(data_start, len(self.raw_df)):
            student_name = self.raw_df.iloc[row_idx, 0]

            # Stop if no student name
            if is_blank(student_name):
                break

            # Extract demographics
            local_id = _clean_id(self.raw_df.iloc[row_idx, 1])
            special_ed = self._yn(self.raw_df.iloc[row_idx, 2])
            emergent_bilingual = self._normalize_eb(self.raw_df.iloc[row_idx, 3])
            ethnicity = str(self.raw_df.iloc[row_idx, 4])

            # Extract MISSED standards only, and build aggregate metrics
            missed_standards: Dict[str, Optional[float]] = {}
            for std, col_idx in zip(metadata['standards'], metadata['standard_columns']):
                score = self.raw_df.iloc[row_idx, col_idx]
                if is_blank(score):
                    # missing data counts as a miss for reporting
                    missed_standards[std] = None
                    self._standard_metrics[std]["missing"] += 1
                else:
                    sc = float(score)
                    if sc >= 1.0:
                        # mastered
                        self._standard_metrics[std]["mastered"] += 1
                        self._standard_metrics[std]["sum"] += 1.0
                        self._standard_metrics[std]["count"] += 1
                    else:
                        # missed
                        missed_standards[std] = sc
                        self._standard_metrics[std]["sum"] += sc
                        self._standard_metrics[std]["count"] += 1

            # Extract summary data conditionally; fallback to computed percent if absent
            scols = metadata.get('summary_columns', {})
            raw_score = None
            percent_score = None
            scale_score = None
            approaches = ''
            meets = ''
            masters = ''

            if 'raw' in scols:
                val = self.raw_df.iloc[row_idx, scols['raw']]
                raw_score = int(val) if not_blank(val) else None
            if 'percent' in scols:
                val = self.raw_df.iloc[row_idx, scols['percent']]
                percent_score = float(val) if not_blank(val) else None
            if 'scale' in scols:
                val = self.raw_df.iloc[row_idx, scols['scale']]
                scale_score = int(val) if not_blank(val) else None
            if 'approaches' in scols:
                approaches = self._yn(self.raw_df.iloc[row_idx, scols['approaches']])
            if 'meets' in scols:
                meets = self._yn(self.raw_df.iloc[row_idx, scols['meets']])
            if 'masters' in scols:
                masters = self._yn(self.raw_df.iloc[row_idx, scols['masters']])

            # If no percent column, compute as average of numeric standard scores
            if percent_score is None:
                numeric_scores = [float(v) for v in missed_standards.values() if v is not None]  # missed are <1.0
                # To compute correctly, we need all standard scores; rebuild for this purpose
                all_scores = []
                for std, col_idx in zip(metadata['standards'], metadata['standard_columns']):
                    val = self.raw_df.iloc[row_idx, col_idx]
                    if not_blank(val):
                        all_scores.append(float(val))
                if all_scores:
                    percent_score = sum(all_scores) / len(all_scores)
                else:
                    percent_score = 0.0
            if raw_score is None:
                # Approximate raw as rounded percent * number of standards (best-effort when absent)
                raw_score = int(round(percent_score * len(metadata['standards']))) if metadata['standards'] else 0

            student = StudentPerformance(
                student_name=str(student_name),
                local_id=local_id,
                special_ed=special_ed,
                emergent_bilingual=emergent_bilingual,
                ethnicity=ethnicity,
                missed_standards=missed_standards,
                raw_score=int(raw_score) if raw_score is not None else 0,
                percent_score=float(percent_score) if percent_score is not None else 0.0,
                scale_score=scale_score,
                approaches=approaches,
                meets=meets,
                masters=masters
            )
            students.append(student)

        return students

    def _calculate_summary(self, students: List[StudentPerformance]) -> AssessmentSummary:
        """Calculate summary statistics"""
        total = len(students)

        if total == 0:
            return AssessmentSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, None)

        approaches_count = sum(1 for s in students if s.approaches == 'y')
        meets_count = sum(1 for s in students if s.meets == 'y')
        masters_count = sum(1 for s in students if s.masters == 'y')

        avg_raw = sum(s.raw_score for s in students) / total
        avg_percent = sum(s.percent_score for s in students) / total

        # Calculate avg scale score if STAAR
        scale_scores = [s.scale_score for s in students if s.scale_score is not None]
        avg_scale = sum(scale_scores) / len(scale_scores) if scale_scores else None

        return AssessmentSummary(
            total_students=total,
            avg_raw_score=round(avg_raw, 2),
            avg_percent_score=round(avg_percent, 4),
            approaches_count=approaches_count,
            approaches_percent=round(100 * approaches_count / total, 2),
            meets_count=meets_count,
            meets_percent=round(100 * meets_count / total, 2),
            masters_count=masters_count,
            masters_percent=round(100 * masters_count / total, 2),
            avg_scale_score=round(avg_scale, 1) if avg_scale else None
        )

    def _analyze_standards(self, students: List[StudentPerformance],
                          standards: List[str]) -> List[StandardAnalysis]:
        """Analyze performance by standard using aggregated metrics built during extraction."""
        analyses = []

        for standard in standards:
            m = self._standard_metrics.get(standard, {"sum": 0.0, "count": 0, "mastered": 0, "missing": 0})
            count = int(m["count"])  # number of students with numeric score
            if count == 0:
                # If no numeric scores, still include with zeros to surface missingness
                avg_score = 0.0
                proficiency_count = 0
                proficiency_rate = 0.0
                total_students = 0
            else:
                avg_score = m["sum"] / count
                proficiency_count = int(m["mastered"])  # mastered means score >= 1.0
                proficiency_rate = 100.0 * proficiency_count / count
                total_students = count

            if self.breakdown_type == "reporting_category":
                std_type = "Reporting Category"
            else:
                std_type = "Readiness" if '[R]' in standard else "Supporting"

            # Check if this maps to Grade 7 STAAR
            # Extract base standard code (e.g., "6.2(B)" -> might map to "7.2(B)")
            grade_7_freq = None
            if standard.startswith('6.'):
                # Try to map 6th grade standard to 7th grade
                potential_7th = standard.replace('6.', '7.')
                base_code = potential_7th.split(' [')[0]  # Remove [R]/[S]
                grade_7_freq = self.GRADE_7_FREQUENCIES.get(base_code)

            analyses.append(StandardAnalysis(
                standard_code=standard,
                canonical_code=self._canonical_teks(standard, self.breakdown_type),
                standard_type=std_type,
                avg_score=round(avg_score, 3),
                proficiency_count=proficiency_count,
                proficiency_rate=round(proficiency_rate, 2),
                total_students=total_students,
                grade_7_staar_frequency=grade_7_freq
            ))

        # Sort by proficiency rate (lowest first - these need intervention)
        analyses.sort(key=lambda x: x.proficiency_rate)

        return analyses

    def _run_quality_checks(self, students: List[StudentPerformance],
                           metadata: Dict) -> Dict:
        """Run data quality checks"""
        checks = {
            'student_count_valid': len(students) > 0,
            'all_students_have_scores': all(s.raw_score is not None for s in students),
            'percent_scores_in_range': all(0 <= s.percent_score <= 1 for s in students),
            'no_missing_standard_data': True,
            'performance_levels_valid': True
        }

        # Check for missing standard scores using aggregated metrics
        for std in metadata['standards']:
            if self._standard_metrics.get(std, {}).get('missing', 0) > 0:
                checks['no_missing_standard_data'] = False
                break

        # Check performance levels
        valid_values = {'y', 'n', ''}
        for student in students:
            if student.approaches not in valid_values or \
               student.meets not in valid_values or \
               student.masters not in valid_values:
                checks['performance_levels_valid'] = False
                break

        return checks


class GenericTabularAssessmentParser:
    """Fallback parser for CSV/XLSX tables with a header row."""

    NAME_CANDIDATES = ["student name", "name", "student"]
    ID_CANDIDATES = ["local id", "student id", "id"]
    SPED_CANDIDATES = ["special ed", "special education", "sped"]
    EB_CANDIDATES = ["eb", "emergent bilingual", "ell", "english learner"]
    ETH_CANDIDATES = ["ethnicity", "eth", "race"]
    PERCENT_CANDIDATES = ["percent score", "percent", "overall percent", "%"]
    RAW_CANDIDATES = ["raw score", "raw", "total correct"]
    APPROACHES_CANDIDATES = ["approaches"]
    MEETS_CANDIDATES = ["meets"]
    MASTERS_CANDIDATES = ["masters"]

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.df = None
        self.validation_issues: List[str] = []
        self._standard_metrics: Dict[str, Dict[str, float]] = {}

    @staticmethod
    def _find_column(columns: List[str], candidates: List[str]) -> Optional[str]:
        for c in columns:
            low = str(c).strip().lower()
            if low in candidates:
                return c
        for c in columns:
            low = str(c).strip().lower()
            for cand in candidates:
                if cand in low:
                    return c
        return None

    @staticmethod
    def _looks_like_standard(col: str) -> bool:
        s = str(col)
        low = s.lower()
        if not s or low in {"nan", ""}:
            return False
        # Exclude obvious summary columns
        if any(token in low for token in ["percent", "score", "total", "raw", "overall", "approaches", "meets", "masters"]):
            return False
        return bool(re.search(r"\d\.", s) or "[" in s or re.search(r"[A-Za-z]\)", s))

    @staticmethod
    def _normalize_score(val) -> Optional[float]:
        if is_blank(val):
            return None
        if isinstance(val, str):
            v = val.strip().replace("%", "")
            if not v:
                return None
            try:
                num = float(v)
            except ValueError:
                return None
        else:
            num = float(val)
        # If value looks like percent (0-100), scale to 0-1
        if num > 1.5:
            num = num / 100.0
        return max(0.0, min(1.0, num))

    def _load(self):
        suffix = self.file_path.suffix.lower()
        if suffix == ".csv":
            self.df = read_csv(self.file_path)
        else:
            self.df = read_xlsx(self.file_path, header=0)

    def parse(self) -> AssessmentData:
        self._load()
        columns = list(self.df.columns)
        name_col = self._find_column(columns, self.NAME_CANDIDATES)
        if not name_col:
            raise ValueError("No student name column found.")
        id_col = self._find_column(columns, self.ID_CANDIDATES)
        sped_col = self._find_column(columns, self.SPED_CANDIDATES)
        eb_col = self._find_column(columns, self.EB_CANDIDATES)
        eth_col = self._find_column(columns, self.ETH_CANDIDATES)
        percent_col = self._find_column(columns, self.PERCENT_CANDIDATES)
        raw_col = self._find_column(columns, self.RAW_CANDIDATES)
        approaches_col = self._find_column(columns, self.APPROACHES_CANDIDATES)
        meets_col = self._find_column(columns, self.MEETS_CANDIDATES)
        masters_col = self._find_column(columns, self.MASTERS_CANDIDATES)

        standard_columns = [c for c in columns if c not in {name_col, id_col, sped_col, eb_col, eth_col,
                                                            percent_col, raw_col, approaches_col, meets_col, masters_col}
                            and self._looks_like_standard(c)]
        if not standard_columns:
            raise ValueError("No standard columns detected. Name your columns like '7.9(F) [S]'.")

        standards = [str(c) for c in standard_columns]
        self._standard_metrics = {
            std: {"sum": 0.0, "count": 0, "mastered": 0, "missing": 0}
            for std in standards
        }

        students: List[StudentPerformance] = []
        for _, row in self.df.iterrows():
            student_name = row.get(name_col)
            if is_blank(student_name) or str(student_name).strip() == "":
                continue

            local_id = _clean_id(row[id_col]) if id_col else ""
            special_ed = EducationDataParser._yn(row[sped_col]) if sped_col else ''
            emergent_bilingual = EducationDataParser._normalize_eb(row[eb_col]) if eb_col else ''
            ethnicity = str(row[eth_col]) if eth_col else ''

            missed_standards: Dict[str, Optional[float]] = {}
            all_scores: List[float] = []
            for std, col in zip(standards, standard_columns):
                score = self._normalize_score(row[col])
                if score is None:
                    missed_standards[std] = None
                    self._standard_metrics[std]["missing"] += 1
                    continue
                all_scores.append(score)
                if score >= 1.0:
                    self._standard_metrics[std]["mastered"] += 1
                    self._standard_metrics[std]["sum"] += 1.0
                    self._standard_metrics[std]["count"] += 1
                else:
                    missed_standards[std] = score
                    self._standard_metrics[std]["sum"] += score
                    self._standard_metrics[std]["count"] += 1

            percent_score = None
            if percent_col:
                percent_score = self._normalize_score(row[percent_col])
            if percent_score is None:
                percent_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
            raw_score = None
            if raw_col:
                raw_val = row[raw_col]
                raw_score = int(raw_val) if not_blank(raw_val) else None
            if raw_score is None:
                raw_score = int(round(percent_score * len(standards))) if standards else 0

            approaches = EducationDataParser._yn(row[approaches_col]) if approaches_col else ''
            meets = EducationDataParser._yn(row[meets_col]) if meets_col else ''
            masters = EducationDataParser._yn(row[masters_col]) if masters_col else ''

            students.append(StudentPerformance(
                student_name=str(student_name),
                local_id=local_id,
                special_ed=special_ed,
                emergent_bilingual=emergent_bilingual,
                ethnicity=ethnicity,
                missed_standards=missed_standards,
                raw_score=int(raw_score) if raw_score is not None else 0,
                percent_score=float(percent_score) if percent_score is not None else 0.0,
                scale_score=None,
                approaches=approaches,
                meets=meets,
                masters=masters
            ))

        metadata = self._build_metadata(standards)
        summary = self._calculate_summary(students)
        standard_analysis = self._analyze_standards(standards)
        validation_report = {
            'file_parsed': str(self.file_path),
            'parse_timestamp': datetime.now().isoformat(),
            'validation_passed': len(self.validation_issues) == 0,
            'issues': self.validation_issues,
            'data_quality_checks': self._run_quality_checks(students, metadata)
        }

        return AssessmentData(
            metadata=metadata,
            students=students,
            summary=summary,
            standard_analysis=standard_analysis,
            validation_report=validation_report
        )

    def _build_metadata(self, standards: List[str]) -> Dict:
        fname = self.file_path.stem
        campus = fname.split("_")[0] if "_" in fname else fname
        grade = None
        m = re.search(r"\b(?:gr|grade|g)(\d)\b", fname, flags=re.IGNORECASE)
        if not m:
            m = re.search(r"\b(\d)\b", fname)
        if m:
            grade = m.group(1)

        readiness = [s for s in standards if '[R]' in s]
        supporting = [s for s in standards if '[S]' in s]
        canonical = [EducationDataParser._canonical_teks(s) for s in standards]

        return {
            'assessment_name': fname,
            'filename': fname,
            'campus': campus,
            'grade': grade,
            'assessment_type': 'Benchmark/Generic',
            'num_standards': len(standards),
            'standards': standards,
            'standard_columns': standards,
            'readiness_standards': readiness,
            'supporting_standards': supporting,
            'canonical_standards': canonical,
            'summary_col_start': None,
            'summary_columns': {}
        }

    def _calculate_summary(self, students: List[StudentPerformance]) -> AssessmentSummary:
        total = len(students)
        if total == 0:
            return AssessmentSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, None)

        approaches_count = sum(1 for s in students if s.approaches == 'y')
        meets_count = sum(1 for s in students if s.meets == 'y')
        masters_count = sum(1 for s in students if s.masters == 'y')

        avg_raw = sum(s.raw_score for s in students) / total
        avg_percent = sum(s.percent_score for s in students) / total

        return AssessmentSummary(
            total_students=total,
            avg_raw_score=round(avg_raw, 2),
            avg_percent_score=round(avg_percent, 4),
            approaches_count=approaches_count,
            approaches_percent=round(100 * approaches_count / total, 2),
            meets_count=meets_count,
            meets_percent=round(100 * meets_count / total, 2),
            masters_count=masters_count,
            masters_percent=round(100 * masters_count / total, 2),
            avg_scale_score=None
        )

    def _analyze_standards(self, standards: List[str]) -> List[StandardAnalysis]:
        analyses = []
        for std in standards:
            m = self._standard_metrics.get(std, {"sum": 0.0, "count": 0, "mastered": 0, "missing": 0})
            count = int(m["count"])
            if count == 0:
                avg_score = 0.0
                proficiency_count = 0
                proficiency_rate = 0.0
                total_students = 0
            else:
                avg_score = m["sum"] / count
                proficiency_count = int(m["mastered"])
                proficiency_rate = 100.0 * proficiency_count / count
                total_students = count
            std_type = "Readiness" if '[R]' in std else "Supporting"
            analyses.append(StandardAnalysis(
                standard_code=std,
                canonical_code=EducationDataParser._canonical_teks(std),
                standard_type=std_type,
                avg_score=round(avg_score, 3),
                proficiency_count=proficiency_count,
                proficiency_rate=round(proficiency_rate, 2),
                total_students=total_students,
                grade_7_staar_frequency=None
            ))
        analyses.sort(key=lambda x: x.proficiency_rate)
        return analyses

    def _run_quality_checks(self, students: List[StudentPerformance], metadata: Dict) -> Dict:
        checks = {
            'student_count_valid': len(students) > 0,
            'all_students_have_scores': all(s.raw_score is not None for s in students),
            'percent_scores_in_range': all(0 <= s.percent_score <= 1 for s in students),
            'no_missing_standard_data': True,
            'performance_levels_valid': True
        }
        for std in metadata['standards']:
            if self._standard_metrics.get(std, {}).get('missing', 0) > 0:
                checks['no_missing_standard_data'] = False
                break
        return checks


class StudentResponsesParser:
    """Parser for 'Student Individual Responses' exports (per-item responses)."""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.df = None
        self.validation_issues: List[str] = []
        self._standard_metrics: Dict[str, Dict[str, float]] = {}

    @staticmethod
    def looks_like_student_responses(file_path: Path) -> bool:
        try:
            preview = read_xlsx(file_path, header=None, nrows=6)
        except Exception:
            return False
        if preview.shape[1] < 6 or preview.shape[0] < 6:
            return False
        header_flag = str(preview.iloc[1, 5]).strip().lower()
        std_row_val = str(preview.iloc[5, 5]).strip()
        return "all responses" in header_flag and bool(std_row_val)

    @staticmethod
    def _parse_max_points(val) -> float:
        if is_blank(val):
            return 1.0
        s = str(val).lower()
        # Look for patterns like "0 to 2" or "0 to 2.5"
        nums = re.findall(r"(\d+(?:\.\d+)?)", s)
        if nums:
            try:
                return float(max(nums, key=lambda x: float(x)))
            except Exception:
                return 1.0
        return 1.0

    # Matches an "n/m" fraction anywhere in a response payload, e.g. "SCR 1/2".
    _FRACTION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")

    @staticmethod
    def _score_from_cell(val, max_points: float) -> Optional[float]:
        if is_blank(val):
            return None
        s = str(val).strip()
        if not s:
            return None
        # A leading '+' means credit was earned; anything else stays 0.0.
        if not s.startswith("+"):
            return 0.0

        payload = s[1:].strip()
        if payload == "":
            return 1.0

        # 1) An explicit "n/m" fraction (e.g. "SCR 1/2") is the ratio itself -
        #    do NOT divide it by max_points again, and do not let a bare
        #    float() parse of the whole payload round it up to full credit.
        m = StudentResponsesParser._FRACTION_RE.search(payload)
        if m:
            numerator = float(m.group(1))
            denominator = float(m.group(2))
            if denominator == 0:
                return 1.0
            return max(0.0, min(numerator / denominator, 1.0))

        # 2) A bare number (e.g. "+5" out of max_points=10) is points earned.
        try:
            credit = float(payload)
        except ValueError:
            # 3) Non-numeric payload (e.g. "+D", "+Multiselect" with no
            #    fraction) means credit was earned with no partial-credit
            #    signal available -> full credit.
            return 1.0

        max_points = max(max_points, 1e-6)
        return max(0.0, min(credit / max_points, 1.0))

    def _load(self):
        self.df = read_xlsx(self.file_path, header=None)

    def parse(self) -> AssessmentData:
        self._load()
        # Student data start is derived from the vertical merge on column A
        # (defaults to row 6, the pre-fix hardcoded value, when undetectable).
        # The TEKS/standard code row is always the last header row, i.e. one
        # row above data_start - this removes the other hardcoded offset
        # (previously a literal row 5) in the same stroke.
        data_start = _data_start_row(self.file_path, default=6)
        standards_row = data_start - 1

        # Identify columns starting at index 5 with standards on standards_row
        standards = []
        question_cols = []
        max_points = {}
        for col in range(5, self.df.shape[1]):
            std = self.df.iloc[standards_row, col]
            if is_blank(std):
                break
            standards.append(str(std))
            question_cols.append(col)
            max_points[col] = self._parse_max_points(self.df.iloc[3, col])

        if not standards:
            raise ValueError("No standards detected in student responses layout.")

        # Group columns by standard for rollups
        std_to_cols: Dict[str, List[int]] = {}
        for std, col in zip(standards, question_cols):
            std_to_cols.setdefault(std, []).append(col)

        self._standard_metrics = {
            std: {"sum": 0.0, "count": 0, "mastered": 0, "missing": 0}
            for std in std_to_cols
        }

        # Summary columns (end-of-row flags)
        summary_cols = {
            'raw': None, 'scale': None, 'percent': None,
            'approaches': None, 'meets': None, 'masters': None
        }
        header_row = 1
        label_map = {
            'raw': ['raw score', 'raw'],
            'scale': ['scale score', 'scale'],
            'percent': ['percent score', 'percent', '%'],
            'approaches': ['approaches'],
            'meets': ['meets'],
            'masters': ['masters']
        }
        for col in range(self.df.shape[1]):
            val = self.df.iloc[header_row, col]
            if isinstance(val, str):
                low = val.strip().lower()
                for key, aliases in label_map.items():
                    if any(a in low for a in aliases):
                        summary_cols[key] = col

        students: List[StudentPerformance] = []
        # Student rows start right at the merge-derived data_start row.
        start_row = data_start
        first_cell = self.df.iloc[start_row, 0] if start_row < len(self.df) else None
        if first_cell is None or is_blank(first_cell) or (isinstance(first_cell, str) and not first_cell.strip()):
            # Fatal for the same reason zero standards is fatal: a run that
            # finds no students still writes a full set of artifacts and a
            # growth snapshot, all of them empty and none of them obviously wrong.
            raise ValueError(
                f"No student rows found in {self.file_path.name} at the expected "
                f"start row ({start_row}). The file layout does not match the "
                "Student Individual Responses report."
            )

        for row_idx in range(start_row, len(self.df)):
            student_name = self.df.iloc[row_idx, 0]
            if is_blank(student_name) or str(student_name).strip() == "":
                break

            local_id = _clean_id(self.df.iloc[row_idx, 1])
            special_ed = EducationDataParser._yn(self.df.iloc[row_idx, 2])
            emergent_bilingual = EducationDataParser._normalize_eb(self.df.iloc[row_idx, 3])
            ethnicity = str(self.df.iloc[row_idx, 4])

            missed_standards: Dict[str, Optional[float]] = {}
            all_scores: List[float] = []

            for std, cols in std_to_cols.items():
                per_std_scores: List[float] = []
                for c in cols:
                    score = self._score_from_cell(self.df.iloc[row_idx, c], max_points[c])
                    if score is None:
                        self._standard_metrics[std]["missing"] += 1
                        continue
                    all_scores.append(score)
                    per_std_scores.append(score)
                if per_std_scores:
                    avg_std = sum(per_std_scores) / len(per_std_scores)
                    if avg_std < 1.0:
                        missed_standards[std] = avg_std
                    self._standard_metrics[std]["sum"] += sum(per_std_scores)
                    self._standard_metrics[std]["count"] += len(per_std_scores)
                    self._standard_metrics[std]["mastered"] += sum(1 for s in per_std_scores if s >= 1.0)
                else:
                    missed_standards[std] = None
                    self._standard_metrics[std]["missing"] += len(cols)

            percent_score = sum(all_scores) / len(all_scores) if all_scores else 0.0
            raw_score = int(round(percent_score * len(std_to_cols))) if std_to_cols else 0
            scale_score = None

            approaches = EducationDataParser._yn(self.df.iloc[row_idx, summary_cols['approaches']]) if summary_cols['approaches'] is not None else ''
            meets = EducationDataParser._yn(self.df.iloc[row_idx, summary_cols['meets']]) if summary_cols['meets'] is not None else ''
            masters = EducationDataParser._yn(self.df.iloc[row_idx, summary_cols['masters']]) if summary_cols['masters'] is not None else ''
            if summary_cols['percent'] is not None:
                val = self.df.iloc[row_idx, summary_cols['percent']]
                if not_blank(val):
                    percent_score = float(val)
                    if percent_score > 1.5:
                        percent_score = percent_score / 100.0
            if summary_cols['raw'] is not None:
                val = self.df.iloc[row_idx, summary_cols['raw']]
                if not_blank(val):
                    raw_score = int(val)
            if summary_cols['scale'] is not None:
                val = self.df.iloc[row_idx, summary_cols['scale']]
                if not_blank(val):
                    scale_score = int(val)

            students.append(StudentPerformance(
                student_name=str(student_name),
                local_id=local_id,
                special_ed=special_ed,
                emergent_bilingual=emergent_bilingual,
                ethnicity=ethnicity,
                missed_standards=missed_standards,
                raw_score=raw_score,
                percent_score=percent_score,
                scale_score=scale_score,
                approaches=approaches,
                meets=meets,
                masters=masters
            ))

        title_cell = self.df.iloc[0, 5] if self.df.shape[1] > 5 else None
        assessment_title = str(title_cell) if not_blank(title_cell) else self.file_path.stem
        grade = None
        m = re.search(r"grade\\s*(\\d)", assessment_title, flags=re.IGNORECASE)
        if m:
            grade = m.group(1)

        metadata = {
            'assessment_name': assessment_title,
            'filename': self.file_path.stem,
            'campus': self.file_path.stem.split("_")[0] if "_" in self.file_path.stem else self.file_path.stem,
            'grade': grade,
            'assessment_type': 'STAAR Responses',
            'num_standards': len(std_to_cols),
            'standards': list(std_to_cols.keys()),
            'standard_columns': question_cols,
            'readiness_standards': [s for s in std_to_cols if '[R]' in s],
            'supporting_standards': [s for s in std_to_cols if '[S]' in s],
            'canonical_standards': [EducationDataParser._canonical_teks(s) for s in std_to_cols],
            'summary_col_start': None,
            'summary_columns': summary_cols,
            'breakdown_type': 'item_response',
        }

        summary = self._calculate_summary(students)
        standard_analysis = self._analyze_standards(metadata['standards'])
        validation_report = {
            'file_parsed': str(self.file_path),
            'parse_timestamp': datetime.now().isoformat(),
            'validation_passed': len(self.validation_issues) == 0,
            'issues': self.validation_issues,
            'data_quality_checks': self._run_quality_checks(students, metadata)
        }

        return AssessmentData(
            metadata=metadata,
            students=students,
            summary=summary,
            standard_analysis=standard_analysis,
            validation_report=validation_report
        )

    def _calculate_summary(self, students: List[StudentPerformance]) -> AssessmentSummary:
        total = len(students)
        if total == 0:
            return AssessmentSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, None)

        approaches_count = sum(1 for s in students if s.approaches == 'y')
        meets_count = sum(1 for s in students if s.meets == 'y')
        masters_count = sum(1 for s in students if s.masters == 'y')

        avg_raw = sum(s.raw_score for s in students) / total
        avg_percent = sum(s.percent_score for s in students) / total

        scale_scores = [s.scale_score for s in students if s.scale_score is not None]
        avg_scale = sum(scale_scores) / len(scale_scores) if scale_scores else None

        return AssessmentSummary(
            total_students=total,
            avg_raw_score=round(avg_raw, 2),
            avg_percent_score=round(avg_percent, 4),
            approaches_count=approaches_count,
            approaches_percent=round(100 * approaches_count / total, 2),
            meets_count=meets_count,
            meets_percent=round(100 * meets_count / total, 2),
            masters_count=masters_count,
            masters_percent=round(100 * masters_count / total, 2),
            avg_scale_score=round(avg_scale, 1) if avg_scale else None
        )

    def _analyze_standards(self, standards: List[str]) -> List[StandardAnalysis]:
        analyses = []
        for std in standards:
            m = self._standard_metrics.get(std, {"sum": 0.0, "count": 0, "mastered": 0, "missing": 0})
            count = int(m["count"])
            if count == 0:
                avg_score = 0.0
                proficiency_count = 0
                proficiency_rate = 0.0
                total_students = 0
            else:
                avg_score = m["sum"] / count
                proficiency_count = int(m["mastered"])
                proficiency_rate = 100.0 * proficiency_count / count
                total_students = count
            std_type = "Readiness" if '[R]' in std else "Supporting"
            analyses.append(StandardAnalysis(
                standard_code=std,
                canonical_code=EducationDataParser._canonical_teks(std),
                standard_type=std_type,
                avg_score=round(avg_score, 3),
                proficiency_count=proficiency_count,
                proficiency_rate=round(proficiency_rate, 2),
                total_students=total_students,
                grade_7_staar_frequency=None
            ))
        analyses.sort(key=lambda x: x.proficiency_rate)
        return analyses

    def _run_quality_checks(self, students: List[StudentPerformance], metadata: Dict) -> Dict:
        checks = {
            'student_count_valid': len(students) > 0,
            'all_students_have_scores': all(s.raw_score is not None for s in students),
            'percent_scores_in_range': all(0 <= s.percent_score <= 1 for s in students),
            'no_missing_standard_data': True,
            'performance_levels_valid': True
        }
        for std in metadata['standards']:
            if self._standard_metrics.get(std, {}).get('missing', 0) > 0:
                checks['no_missing_standard_data'] = False
                break
        return checks


def pick_parser(file_path):
    """Return (parser_instance, human_label) for a given assessment export.

    Single shared implementation used by both webui.py and batch_processor.py
    so the two entry points cannot drift out of sync again (that drift is
    exactly how StudentResponsesParser ended up permanently shadowed).

    Order: detect_report_type() reads the Excel F2 report-type label and,
    when it recognizes one of the three known Eduphoria Aware exports, wins
    definitively. Only when it returns None (unknown/legacy/non-Eduphoria
    file) do we fall back to the older shape-sniffing heuristics, in their
    original order, so behavior for files this fix doesn't target is
    unchanged.
    """
    file_path = Path(file_path)
    is_xlsx = file_path.suffix.lower() == ".xlsx"

    if is_xlsx:
        report_type = detect_report_type(file_path)
        if report_type == "learning_standard":
            return (
                EducationDataParser(str(file_path), breakdown_type="learning_standard"),
                "Student Learning Standard Breakdown",
            )
        if report_type == "reporting_category":
            return (
                EducationDataParser(str(file_path), breakdown_type="reporting_category"),
                "Student Reporting Category Breakdown",
            )
        if report_type == "item_response":
            return StudentResponsesParser(str(file_path)), "Student Individual Responses"

        # Legacy fallback heuristics (kept in their historical order).
        if EducationDataParser.looks_like_eduphoria(file_path):
            return EducationDataParser(str(file_path)), "Eduphoria standard breakdown"
        if StudentResponsesParser.looks_like_student_responses(file_path):
            return StudentResponsesParser(str(file_path)), "Student individual responses"

    return GenericTabularAssessmentParser(str(file_path)), "Generic tabular"


def convert_to_json(assessment_data: AssessmentData, output_path: Optional[str] = None) -> str:
    """Convert assessment data to a compact JSON format for token efficiency."""
    # The anonymizer is injected via metadata to avoid breaking signature
    anonymizer: Optional["VaultIdentity"] = assessment_data.metadata.get('_anonymizer')

    md = assessment_data.metadata

    # Strip demographic quasi-identifiers (race/ethnicity, SPED, EB) so that
    # "anonymized" output is genuinely de-identified, not just name-swapped.
    # These fields, combined with scores in a small class, can re-identify a
    # student. Defaults to ON whenever an anonymizer is active; callers can
    # override via metadata['_strip_demographics'].
    strip_demographics = md.get('_strip_demographics')
    if strip_demographics is None:
        strip_demographics = anonymizer is not None

    def student_to_compact(s: StudentPerformance) -> Dict:
        if anonymizer:
            # One call, so the map records that this name and this id are the
            # same student. That link is what a Canvas crosswalk joins on.
            name, anon_id = anonymizer.map_student(s.student_name, s.local_id)
        else:
            name, anon_id = s.student_name, s.local_id

        # shorten keys and values
        obj = {
            'n': name,                    # name (anonymized if enabled)
            'id': anon_id,                # local id (anonymized if enabled)
        }
        if not strip_demographics:
            obj['sped'] = s.special_ed         # special education (y/n)
            obj['eb'] = s.emergent_bilingual   # EB code (y/n/1st/2nd/fmr/...)
            obj['eth'] = s.ethnicity           # ethnicity
        obj.update({
            'raw': s.raw_score,            # raw score
            'pct': round(s.percent_score * 100, 2),  # percent as 0-100 rounded
            # omit scale score if None to save space
            'app': s.approaches,           # approaches (y/n)
            'met': s.meets,                # meets (y/n) – optional but kept for clarity
            'mas': s.masters,              # masters (y/n)
            'missed': {std: round(score * 100, 2) if score is not None else None
                      for std, score in s.missed_standards.items()}  # missed standards with % correct (0-100)
        })
        if s.scale_score is not None:
            obj['ss'] = s.scale_score
        return obj

    note = 'Scores in missed[] are PERCENT CORRECT (0-100), not percent missed.'
    if strip_demographics:
        note += ' Demographic fields (race/ethnicity, SPED, EB) removed for de-identification.'

    output = {
        'meta': {
            'name': md.get('assessment_name'),
            'camp': md.get('campus'),
            'gr': md.get('grade'),
            'type': md.get('assessment_type'),
            'standards': md.get('standards'),
            'canonical': md.get('canonical_standards'),
            'anonymized': anonymizer is not None,
            'demographics_removed': bool(strip_demographics),
            '_note': note,
        },
        'students': [student_to_compact(s) for s in assessment_data.students]
    }

    json_str = json.dumps(output, ensure_ascii=False)
    assert_no_leaks(json_str, anonymizer, "the LLM-ready JSON")

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(json_str)

    return json_str


def create_llm_friendly_summary(assessment_data: AssessmentData) -> str:
    """Create a brief text summary optimized for LLM context windows."""

    md = assessment_data.metadata
    sm = assessment_data.summary

    summary = f"""# {md['assessment_name']}

- Campus: {md['campus']} | Grade: {md['grade']} | Type: {md['assessment_type']}
- Students: {sm.total_students} | Avg: {sm.avg_percent_score*100:.1f}%
- Standards: {md['num_standards']} (R: {len(md['readiness_standards'])}, S: {len(md['supporting_standards'])})

Tip: Only missed standards are listed per student. Unlisted = mastered.
"""
    return summary


def create_teacher_report(assessment_data: AssessmentData) -> str:
    """Create a teacher-facing TXT listing each missed standard with student names under it."""
    anonymizer: Optional["VaultIdentity"] = assessment_data.metadata.get('_anonymizer')
    md = assessment_data.metadata
    students = assessment_data.students

    # Build map: standard -> [(student name, percent correct)]
    missed_map: Dict[str, List[tuple]] = {std: [] for std in md['standards']}
    for s in students:
        for std, score in s.missed_standards.items():
            pct_str = f"{score*100:.1f}%" if score is not None else "missing"
            name = anonymizer.map_name(s.student_name) if anonymizer else s.student_name
            missed_map.setdefault(std, []).append((name, pct_str))

    # Sort standards by number of misses (desc), then by code
    sorted_items = sorted(
        missed_map.items(),
        key=lambda kv: (-len(kv[1]), kv[0])
    )

    lines: List[str] = []
    lines.append(f"Assessment: {md['assessment_name']}")
    lines.append(f"Campus: {md['campus']} | Grade: {md['grade']} | Type: {md['assessment_type']}")
    lines.append(f"Students: {len(students)}")
    lines.append("")
    if anonymizer:
        lines.append("Names are pseudonyms (the Identity Vault is kept locally).")
        lines.append("")
    lines.append("NOTE: Scores shown are PERCENT CORRECT on that standard.")
    lines.append("Only students who scored below 100% on a standard are listed.")
    lines.append("")

    for std, entries in sorted_items:
        # Skip standards with zero misses
        if not entries:
            continue
        lines.append(std)
        for name, pct in sorted(entries, key=lambda x: x[0]):
            lines.append(f"  - {name}: {pct}")
        lines.append("")

    # If nothing was missed at all
    if all(len(v) == 0 for v in missed_map.values()):
        lines.append("All students mastered all listed standards.")

    return assert_no_leaks("\n".join(lines), anonymizer, "the teacher report")


def create_parent_narratives(assessment_data: AssessmentData, top_n: int = 3) -> str:
    """Create brief, local-generated narratives per student to reduce LLM load."""
    anonymizer: Optional["VaultIdentity"] = assessment_data.metadata.get('_anonymizer')
    md = assessment_data.metadata
    students = assessment_data.students
    standards = md.get('standards', [])

    # Map standard -> overall proficiency rate to prioritize focus areas
    std_to_proficiency = {a.standard_code: a.proficiency_rate for a in assessment_data.standard_analysis}

    lines: List[str] = []
    lines.append(f"Assessment: {md.get('assessment_name')}")
    lines.append(f"Campus: {md.get('campus')} | Grade: {md.get('grade')} | Type: {md.get('assessment_type')}")
    lines.append("")
    lines.append("Parent/Student Narratives (auto-generated locally)")
    lines.append("Scores are percent correct; standards not listed were mastered (100%).")
    lines.append("")

    for s in students:
        name = anonymizer.map_name(s.student_name) if anonymizer else s.student_name
        lines.append(f"{name} — Overall {s.percent_score*100:.1f}%")

        # Rank missed standards by (low) score then by overall proficiency to surface biggest needs
        missed_items = []
        for std, score in s.missed_standards.items():
            pct = score * 100 if score is not None else 0.0
            prof = std_to_proficiency.get(std, 100.0)
            missed_items.append((pct, prof, std))
        missed_items.sort(key=lambda x: (x[0], x[1]))

        focus = missed_items[:top_n]
        if focus:
            lines.append("  Focus standards:")
            for pct, prof, std in focus:
                lines.append(f"    - {std}: {pct:.1f}% (campus proficiency: {prof:.1f}%)")
        else:
            lines.append("  Focus standards: none (all at 100%)")

        lines.append("")

    return assert_no_leaks("\n".join(lines), anonymizer, "the parent narratives")


def main():
    """Command-line interface"""
    if len(sys.argv) < 2:
        print("Usage: python -m dataforge.eduphoria_parser <input_file.xlsx> [output_file.json]")
        print("\nThis tool converts Eduphoria XLSX files to LLM-friendly JSON format.")
        print("\nOptions:")
        print("  - If no output file specified, prints to stdout")
        print("  - Creates both .json and .md (summary) files")
        sys.exit(1)

    input_file = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Parsing: {input_file}")
    print("=" * 80)

    try:
        parser = EducationDataParser(input_file)
        data = parser.parse()
        from .identity import VaultIdentity
        from .paths import get_paths
        identity = VaultIdentity.from_paths(get_paths())
        data.metadata['_anonymizer'] = identity

        # Create JSON output
        json_output = convert_to_json(data, output_json)

        if not output_json:
            print(json_output)
        else:
            print(f"✓ JSON saved to: {output_json}")

            # Also create markdown summary
            md_path = output_json.replace('.json', '.md')
            md_summary = create_llm_friendly_summary(data)
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_summary)
            print(f"✓ Summary saved to: {md_path}")

        # Print validation report
        print("\n" + "=" * 80)
        print("VALIDATION REPORT")
        print("=" * 80)

        vr = data.validation_report
        status = "✓ PASSED" if vr['validation_passed'] else "⚠ ISSUES FOUND"
        print(f"Status: {status}")

        if vr['issues']:
            print("\nIssues:")
            for issue in vr['issues']:
                print(f"  - {issue}")

        print("\nData Quality Checks:")
        for check, passed in vr['data_quality_checks'].items():
            symbol = "✓" if passed else "✗"
            print(f"  {symbol} {check}")

        # Print quick summary
        print("\n" + "=" * 80)
        print(create_llm_friendly_summary(data))

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
