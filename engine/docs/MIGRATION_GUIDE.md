# QuizForge Migration Guide

> **Historical record.** Documents the **completed** Nov 2025 restructure from a
> nested `Packager/quizforge/` layout to the flat `engine/` layout. The current
> structure and design are in [`../../dev/ARCHITECTURE.md`](../../dev/ARCHITECTURE.md).
> Since this migration, a third backend — **QuizForge-API** (`api/`) — was added;
> it is not covered here (see the root `AGENTS.md`).

## Overview

QuizForge was restructured from a nested `Packager/quizforge/` layout to a flat
`engine/` layout for better maintainability and LLM agent navigation.

## Migration Summary

### Old Structure → New Structure

| Old Location | New Location | Changes |
|--------------|--------------|---------|
| `Packager/quizforge/domain/quiz.py` | `engine/core/quiz.py` | Added helper methods |
| `Packager/quizforge/domain/questions.py` | `engine/core/questions.py` | Extracted NumericalAnswer |
| `Packager/quizforge/domain/questions.py` | `engine/core/answers.py` | NumericalAnswer moved here |
| `Packager/quizforge/io/parsers/text_parser.py` | `engine/parsing/text_parser.py` | Updated imports |
| `Packager/quizforge/renderers/qti/` | `engine/rendering/canvas/` | Reorganized, updated imports |
| `Packager/quizforge/services/validation.py` | `engine/validation/` | Expanded into full layer |
| `Packager/quizforge/services/packager.py` | `engine/orchestrator.py` | Enhanced workflow |

### New Components

These did not exist in the old structure:

- `engine/validation/` - Full validation layer with rules and auto-fixers
- `engine/feedback/` - User-facing message generation
- `engine/packaging/` - Output folder management
- `engine/rendering/physical/` - Physical quiz rendering

## Key Architectural Changes

### 1. Validation is Now a Dedicated Layer

**Old**: Validation was scattered across parser and packager.

**New**: Dedicated validation layer with:
- Structure rules (hard fails)
- Fairness rules (soft fails)
- Auto-fixers (point normalization, choice shuffling)

### 2. Clear Separation of Concerns

**Old**: Parser did some validation, packager did some validation.

**New**:
- Parser: TXT → Quiz (minimal validation)
- Validator: Quiz → Validated Quiz (all validation)
- Renderers: Validated Quiz → Output (no validation)

### 3. Feedback Generation

**Old**: Orchestrator printed messages to console.

**New**: Dedicated feedback generators create files:
- Success logs (`log_PASS_FIXED.txt`)
- Fail prompts (`Quiz_FAIL_REVISE_WITH_AI.txt`)

## Import Path Changes

```python
# OLD
from Packager.quizforge.domain.quiz import Quiz
from Packager.quizforge.domain.questions import MCQuestion, NumericalAnswer
from Packager.quizforge.io.parsers.text_parser import TextOutlineParser

# NEW
from engine.core.quiz import Quiz
from engine.core.questions import MCQuestion
from engine.core.answers import NumericalAnswer
from engine.parsing.text_parser import TextOutlineParser
```

## Breaking Changes

### None (for users)

The user-facing interface (DropZone → run_quizforge → Finished_Exports) is unchanged.

### For Developers

If you were importing from `Packager/quizforge/`, update your imports as shown above.

## Timeline

- Planning: October 2025
- Implementation: TASK_001 through TASK_010 (November 2025)
- Verification: November 16, 2025 (see `VERIFICATION_CHECKLIST.md`)
- Old code removal: completed (no `Packager/` directory remains)

## Questions?

See:
- [`../../dev/ARCHITECTURE.md`](../../dev/ARCHITECTURE.md) — current system design
- [`../../dev/AGENT_MAP.md`](../../dev/AGENT_MAP.md) — navigation guide for LLM agents
- root `AGENTS.md` — project orientation (three backends)
