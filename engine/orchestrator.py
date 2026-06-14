"""Main orchestrator for the QuizForge pipeline.

This module coordinates the entire workflow:
1. Scan DropZone for new quiz files
2. Parse TXT/JSON/MD text into a Quiz object
3. Validate and auto-fix Quiz
4. Route to appropriate packagers based on validation status
5. Generate user-facing output (packages or revision prompts)
6. Clean up and archive processed files

The orchestrator is the only component that performs file I/O in user directories.
All other modules work with in-memory data structures.
"""


from pathlib import Path
from typing import List, Optional
import shutil

from .importers import JsonImportError, import_quiz_from_llm
from .config import SPEC_MODE
from .validation.validator import QuizValidator, ValidationStatus
from .packagers.packager import package_quiz
from .packaging.folder_creator import create_quiz_folder, write_file
from .feedback.log_generator import generate_log
from .feedback.fail_prompt_generator import generate_fail_prompt
from .spec_engine import parser as spec_parser


ALLOWED_INPUT_EXTENSIONS = {".txt", ".json", ".md"}


class QuizForgeOrchestrator:
    """Coordinate the quiz processing pipeline."""
    
    def __init__(self, dropzone_path: str, output_path: str, force: bool = False):
        """Initialize orchestrator with input/output paths.
        
        Args:
            dropzone_path: Path to DropZone directory (user input)
            output_path: Path to Finished_Exports directory (user output)
            force: If True, demote length-bias FAIL to WEAK_PASS warning
        """
        self.dropzone = Path(dropzone_path)
        self.output = Path(output_path)
        self.archive = self.dropzone / "old_quizzes"
        
        # Ensure directories exist
        self.dropzone.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        self.archive.mkdir(parents=True, exist_ok=True)
        
        self.force = force

        # Initialize components
        self.validator = QuizValidator()
    
    def process_all(self) -> None:
        """Scan DropZone and process all supported text files."""
        input_files = self._get_input_files()
        
        if not input_files:
            print("No quiz files found in DropZone.")
            return
        
        print(f"Found {len(input_files)} quiz file(s) to process...")
        print()
        
        for filepath in input_files:
            print(f"Processing: {filepath.name}")
            try:
                self.process_file(filepath)
                print(f"  -> Success")
            except Exception as e:
                print(f"  -> Error: {e}")
            print()
    
    def process_file(self, filepath: Path) -> None:
        """Process a single quiz file through the pipeline.
        
        Args:
            filepath: Path to quiz file (.txt/.json/.md)
        """
        # Read original text (for fail prompts)
        original_text = filepath.read_text(encoding='utf-8')
        
        # Step 1: Parse
        try:
            imported = import_quiz_from_llm(original_text)
            quiz = imported.quiz
        except Exception as e:
            context = None
            if isinstance(e, JsonImportError):
                context = self._format_json_error_context(original_text, e)
            # Parser failed - create fail prompt
            self._handle_parse_failure(filepath, original_text, str(e), context, parse_exc=e)
            return
        
        # Step 2a: Calculate point values for quiz (automated)
        try:
            from engine.validation.point_calculator import calculate_points
            from engine.validation.answer_balancer import balance_answers
            from engine.rendering.physical.styles.default_styles import DEFAULT_QUIZ_POINTS
            # Calculate points
            quiz.questions = calculate_points(quiz.questions, total_points=DEFAULT_QUIZ_POINTS)
            # Balance answers (no log path available yet)
            quiz.questions = balance_answers(quiz.questions)
        except Exception:
            # On failure, continue without recalculation/balancing
            pass

        # Step 2b: Validate
        result = self.validator.validate(quiz)
        
        # Step 3: Route based on status
        if result.status == ValidationStatus.FAIL:
            if self.force and result.quiz is not None and result.fix_log is not None:
                # Demote length-bias hard-fail to a warning and proceed
                from .validation.validator import ValidationResult
                forced_result = ValidationResult(
                    status=ValidationStatus.WEAK_PASS,
                    quiz=result.quiz,
                    fix_log=result.fix_log,
                    errors=[],
                    warnings=[f"[FORCED] {e}" for e in result.errors],
                )
                print(f"  -> FORCED override: length-bias check bypassed (not a clean pass)")
                self._handle_validation_success(filepath, forced_result, forced=True)
            else:
                self._handle_validation_failure(filepath, original_text, result)
        else:
            self._handle_validation_success(filepath, result)
    
    def _handle_parse_failure(
        self,
        filepath: Path,
        original_text: str,
        error: str,
        context: Optional[str] = None,
        parse_exc: Optional[Exception] = None,
    ) -> None:
        """Handle parser failure by creating fail prompt."""
        quiz_name = filepath.stem
        primary_error = f"Parse error: {error}"
        if context:
            primary_error = f"{primary_error}\nContext:\n{context}"
        errors = [primary_error]
        lint_errors = getattr(parse_exc, "lint_errors", []) if parse_exc else []
        errors.extend(lint_errors)
        
        # Generate fail prompt
        prompt = generate_fail_prompt(
            original_text=original_text,
            errors=errors,
            quiz_title=quiz_name
        )
        
        # Write fail prompt to output
        fail_filename = f"{quiz_name}_FAIL_REVISE_WITH_AI.txt"
        fail_path = self.output / fail_filename
        fail_path.write_text(prompt, encoding='utf-8')
        
        print(f"  -> Created: {fail_filename}")
        
        # Archive original file
        self._archive_file(filepath)
    
    def _handle_validation_failure(self, filepath: Path, original_text: str, result) -> None:
        """Handle validation failure by creating fail prompt."""
        quiz_name = filepath.stem
        
        # Generate fail prompt
        prompt = generate_fail_prompt(
            original_text=original_text,
            errors=result.errors,
            quiz_title=result.quiz.title
        )
        
        # Write fail prompt to output
        fail_filename = f"{quiz_name}_FAIL_REVISE_WITH_AI.txt"
        fail_path = self.output / fail_filename
        fail_path.write_text(prompt, encoding='utf-8')
        
        print(f"  -> Created: {fail_filename}")
        
        # Archive original file
        self._archive_file(filepath)
    
    def _handle_validation_success(self, filepath: Path, result, forced: bool = False) -> None:
        """Handle validation success by generating packages."""
        quiz = result.quiz
        quiz_name = filepath.stem
        
        # Create output folder
        folder = create_quiz_folder(self.output, quiz.title)
        
        # Generate packages (both Canvas and Physical)
        try:
            package_results = package_quiz(quiz, str(folder))
            
            # Report successful outputs to user
            if package_results.get('canvas'):
                canvas = package_results['canvas']
                print(f"  -> Created: {folder.name}/{Path(canvas['qti_path']).name}")
            
            if package_results.get('physical'):
                phys = package_results['physical']
                print(f"  -> Created: {folder.name}/{Path(phys['quiz_path']).name}")
                print(f"  -> Created: {folder.name}/{Path(phys['key_path']).name}")
                print(f"  -> Created: {folder.name}/{Path(phys['rationale_path']).name}")
            
            print(f"  -> All outputs saved to: {folder.name}")
            
        except Exception as e:
            print(f"  -> Packaging failed: {e}")
            # Could create error log here if needed
            return
        
        # Generate success log
        if forced:
            log_filename = "log_FORCED_WEAK_PASS.txt"
        elif result.status == ValidationStatus.PASS:
            log_filename = "log_PASS_FIXED.txt"
        else:
            log_filename = "log_WEAK_PASS_FIXED.txt"
        log_content = generate_log(
            fix_log=result.fix_log,
            warnings=result.warnings,
            quiz_title=quiz.title,
            total_points=quiz.total_points(),
            question_count=quiz.question_count()
        )
        if forced:
            force_banner = (
                "!!! FORCED OUTPUT — LENGTH-BIAS CHECK BYPASSED !!!\n"
                "This quiz was pushed through with --force and did NOT pass\n"
                "the length-bias validation. Correct answers are consistently\n"
                "the longest choice. Do not distribute as a validated quiz.\n"
                "=" * 60 + "\n\n"
            )
            log_content = force_banner + log_content
        log_path = folder / log_filename
        write_file(folder, log_filename, log_content.encode('utf-8'))

        # Append physical validation stats into the main log (then remove the extra file)
        try:
            phys_log_path = None
            if package_results.get('physical'):
                phys_log_path = package_results['physical'].get('log_path')
            if phys_log_path:
                phys_text = Path(phys_log_path).read_text(encoding='utf-8')
                with log_path.open('a', encoding='utf-8') as lf:
                    lf.write('\n\n' + phys_text.strip() + '\n')
                Path(phys_log_path).unlink(missing_ok=True)
        except Exception:
            pass

        # Append answer distribution stats into the main log instead of a separate file
        try:
            from engine.validation.answer_balancer import distribution_stats_text
            dist_text = distribution_stats_text(quiz.questions)
            with log_path.open('a', encoding='utf-8') as lf:
                lf.write('\n\n' + dist_text.strip() + '\n')
        except Exception:
            pass

        print(f"  -> Created: {folder.name}/{log_filename}")
        
        # Archive original file
        self._archive_file(filepath)
    
    def _format_json_error_context(self, original_text: str, error: JsonImportError) -> Optional[str]:
        """Return a caret-highlighted line for JSON parse errors."""
        line = getattr(error, "line", None)
        column = getattr(error, "column", None)
        if not isinstance(line, int) or not isinstance(column, int) or line < 1 or column < 1:
            return None

        try:
            payload = spec_parser.extract_tagged_payload(original_text)
        except Exception:
            payload = original_text

        lines = payload.splitlines()
        if not lines or line > len(lines):
            return None

        line_text = lines[line - 1]
        prefix = f"{line:04d}: "
        caret_offset = min(max(column - 1, 0), max(len(line_text), 0))
        caret_line = " " * (len(prefix) + caret_offset) + "^"
        return f"{prefix}{line_text}\n{caret_line}"

    def _archive_file(self, filepath: Path) -> None:
        """Move processed file to archive folder."""
        dest = self.archive / filepath.name
        
        # Handle name collision
        if dest.exists():
            counter = 1
            while dest.exists():
                dest = self.archive / f"{filepath.stem}_{counter}{filepath.suffix}"
                counter += 1
        
        shutil.move(str(filepath), str(dest))

    def _get_input_files(self) -> List[Path]:
        """Return all supported text-like files in the DropZone."""
        files: List[Path] = []
        for path in sorted(self.dropzone.iterdir()):
            if path.is_file() and path.suffix.lower() in ALLOWED_INPUT_EXTENSIONS:
                files.append(path)
        return files


def main():
    """Entry point for command-line execution."""
    import sys
    
    # Get project root (where DropZone and Finished_Exports live)
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        project_root = Path(args[0])
    else:
        # Assume we're in QuizForge/engine/
        project_root = Path(__file__).parent.parent
    
    dropzone = project_root / "DropZone"
    output = project_root / "Finished_Exports"
    
    print("=" * 60)
    print("QuizForge Processing Pipeline")
    print("=" * 60)
    print(f"DropZone: {dropzone}")
    print(f"Output: {output}")
    print("=" * 60)
    if force:
        print()
        print("!!! WARNING: --force flag is active !!!")
        print("Length-bias failures will be bypassed. This is NOT")
        print("a substitute for properly balanced answer choices.")
        print("Output logs will be stamped FORCED_WEAK_PASS.")
        print("=" * 60)
    print()

    orchestrator = QuizForgeOrchestrator(
        dropzone_path=str(dropzone),
        output_path=str(output),
        force=force
    )
    
    orchestrator.process_all()
    
    print("=" * 60)
    print("Processing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
