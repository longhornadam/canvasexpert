"""AI-TA library generator for paste-ready MagicSchool / Copilot skill files.

Pure module: builds plain-text output files only. The web UI / server owns the
HTTP routes and startup hook.
"""
import os

from . import rf

from api import runtime_paths
from engine.utils.text_utils import safe_filename_component


MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
API_DIR = os.path.dirname(MODULE_DIR)
REPO_ROOT = os.path.dirname(API_DIR)
DEFAULT_DOCS_DIR = os.path.join(API_DIR, "default_docs")
DEFAULT_AI_TA_DIR = os.path.join(DEFAULT_DOCS_DIR, "AI-TA")
QUIZFORGE_EXPLAINER_PATH = os.path.join(REPO_ROOT, "LLM_Modules", "QuizForge_Explainer.txt")
CONTRACT_FILES = {
    "Author a Quiz (QuizForge).txt": ("quiz", "QUIZFORGE_JSON", os.path.join(REPO_ROOT, "LLM_Modules", "QuizForge_Base.md")),
    "Author an Assignment (AssignmentForge).txt": ("assignment", "ASSIGNMENTFORGE_JSON", os.path.join(REPO_ROOT, "LLM_Modules", "AssignmentForge_Base.md")),
    "Author a Page (PageForge).txt": ("page", "PAGEFORGE_JSON", os.path.join(REPO_ROOT, "LLM_Modules", "PageForge_Base.md")),
    "Author a Rubric (RubricForge).txt": ("rubric", "RUBRICFORGE_JSON", os.path.join(REPO_ROOT, "LLM_Modules", "RubricForge_Base.md")),
    "Author a TA (TAForge).txt": ("TA persona", "TAFORGE_JSON", os.path.join(REPO_ROOT, "LLM_Modules", "TAForge_Base.md")),
}


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _write_text_if_missing(path, text):
    """Seed a file once and preserve teacher edits on later runs."""
    if os.path.exists(path):
        return False
    _write_text(path, text)
    return True


def _copy_tree_if_missing(source_dir, dest_dir):
    written = []
    if not os.path.isdir(source_dir):
        return written
    for root, _, files in os.walk(source_dir):
        rel_dir = os.path.relpath(root, source_dir)
        target_root = dest_dir if rel_dir == "." else os.path.join(dest_dir, rel_dir)
        os.makedirs(target_root, exist_ok=True)
        for name in files:
            src = os.path.join(root, name)
            dest = os.path.join(target_root, name)
            if os.path.exists(dest):
                continue
            import shutil
            shutil.copy2(src, dest)
            written.append(dest)
    return written


def _make_start_here_text():
    preamble = (
        "PASTE THIS WHOLE FILE INTO YOUR AI ASSISTANT (MagicSchool, Copilot, etc.).\n\n"
        "You are a friendly guide for a teacher who uses (or is curious about) Canvas\n"
        "Expert and its Forge tools. The reference document below explains the whole\n"
        "system. Read it, then answer the teacher's questions in plain language, with\n"
        "short answers first and detail only when asked. If a question goes beyond the\n"
        "document, say so honestly rather than guessing.\n\n"
        "=== REFERENCE DOCUMENT ===\n"
    )
    return preamble + _read_text(QUIZFORGE_EXPLAINER_PATH).rstrip() + "\n"


def _make_authoring_text(kind, tag, contract_path):
    preamble = (
        "PASTE THIS WHOLE FILE INTO YOUR AI ASSISTANT (MagicSchool, Copilot, etc.),\n"
        f"THEN DESCRIBE THE {kind.upper()} YOU WANT.\n\n"
        f"You are an expert {kind} author for a real teacher. The contract below defines\n"
        f"EXACTLY how your final output must be formatted. Converse with the teacher\n"
        f"about what they need; when the {kind} is ready, output it as one JSON object\n"
        f"between <{tag}> and </{tag}> tags, exactly as the contract specifies.\n\n"
        "The teacher will save your output as a .txt file and load it into Canvas\n"
        "Expert, which pushes it into Canvas for them — so format obedience matters\n"
        "more than anything else.\n\n"
        "=== THE CONTRACT ===\n"
    )
    return preamble + _read_text(contract_path).rstrip() + "\n"


def _sanitize_filename(text):
    return safe_filename_component(text, fallback="Rubric")


def _make_rubric_score_text(data):
    return rf.scoring_prompt(data).rstrip() + "\n"


def _about_text():
    return (
        "AI-TA Library\n\n"
        "This folder contains paste-ready single-file skills for MagicSchool.ai and\n"
        "M365 Copilot. Paste one whole file into your chat assistant, then keep the\n"
        "conversation inside that one file's instructions.\n\n"
        "File categories:\n"
        "- START HERE: Canvas Expert overview and how the system fits together.\n"
        "- Authoring skills: one file each for QuizForge, AssignmentForge, PageForge, RubricForge, and TAForge.\n"
        "- Scoring skills: one file per valid rubric in the default rubric library.\n\n"
        "Canvas Expert seeds missing files in this folder, then leaves existing files\n"
        "alone so you can refine them by hand in VS Code.\n"
    )


def _make_essay_scorer_instructions():
    return (
        "PASTE THIS WHOLE FILE INTO YOUR AI ASSISTANT (MagicSchool, Copilot, etc.).\n\n"
        "You are an experienced teacher scoring student writing. A rubric file is attached\n"
        "as Knowledge. Use it exclusively — do not invent criteria.\n\n"
        "SCORING RULES:\n"
        "- Read the rubric's scoring_guidance section carefully before scoring.\n"
        "- Score each criterion independently.\n"
        "- Use the full range — a response can be excellent in one criterion and weak\n"
        "  in another.\n"
        "- Quote briefly from the student's work to justify every score.\n"
        "- Return your evaluation as JSON matching the rubric's output_template exactly,\n"
        "  then a short plain-English summary the student could read.\n"
        "- Wait for one pasted student response at a time before scoring.\n\n"
        "The rubric attached as Knowledge defines all criteria, rating labels, point\n"
        "values, and the exact output_template format. Follow it obediently.\n\n"
        "I will paste one student response at a time. Wait for it.\n"
    )


_TOOLKIT_TOOLS = {
    "Quiz Author": {
        "file":        "Author a Quiz (QuizForge).txt",
        "description": "Helps a teacher author a Canvas-ready QuizForge JSON quiz from a description.",
        "knowledge":   ["Quiz Author — KNOWLEDGE QuizForge_example_quiz.txt",
                        "Quiz Author — KNOWLEDGE QF_MOD_ELA_Question_Design.txt"],
        "knowledge_sources": [
            os.path.join(REPO_ROOT, "LLM_Modules", "QuizForge_example_quiz.txt"),
            os.path.join(REPO_ROOT, "LLM_Modules", "QF_MOD_ELA_Question_Design.md"),
        ],
        "customize": [
            "My students are [grade level] [subject] students.",
            "I typically include [number] questions per quiz.",
        ],
    },
    "Assignment Author": {
        "file":        "Author an Assignment (AssignmentForge).txt",
        "description": "Helps a teacher author a Canvas-ready AssignmentForge JSON assignment.",
        "knowledge":   [],
        "knowledge_sources": [],
        "customize": [
            "My classes are [grade level] [subject].",
            "I usually assign [points] points for major assignments.",
        ],
    },
    "Page Author": {
        "file":        "Author a Page (PageForge).txt",
        "description": "Helps a teacher author a Canvas-ready PageForge JSON unit hub or resource page.",
        "knowledge":   [],
        "knowledge_sources": [],
        "customize": [
            "My class pages use the following heading style: [describe style].",
            "My course is [course name] for [grade level] students.",
        ],
    },
    "Rubric Author": {
        "file":        "Author a Rubric (RubricForge).txt",
        "description": "Helps a teacher author a Canvas-ready RubricForge JSON rubric with student explainer and scoring guidance.",
        "knowledge":   [],
        "knowledge_sources": [],
        "customize": [
            "My rubrics should use [number] criteria and [number] rating levels.",
            "My default total is [points] points.",
        ],
    },
    "Essay Scorer": {
        "file":        None,          # generated inline, not from CONTRACT_FILES
        "description": "Scores student essays using a rubric file attached as Knowledge.",
        "knowledge":   ["(your rubric .txt file from the Rubrics folder — e.g. ELA7_Classroom_Writing_Rubric.txt)"],
        "knowledge_sources": [],
        "customize": [
            "My students are [grade level] [subject].",
            "I want feedback language suitable for [audience: students / teacher].",
        ],
    },
}


def _make_setup_text(tool_name, info, instructions_filename):
    lines = [
        f"MagicSchool Custom Tool: {tool_name}",
        "=" * 60,
        "",
        f"Suggested Tool Name: {tool_name}",
        f"Suggested Tool Description: {info['description']}",
        "",
        "Instructions (upload or paste):",
        f"  File: {instructions_filename}",
        "  (Upload this file in the Instructions field, or paste its entire contents.)",
        "",
    ]
    if info["knowledge"]:
        lines.append("Knowledge file(s) to attach:")
        for kf in info["knowledge"]:
            lines.append(f"  - {kf}")
        lines.append("  (Attach these in the Knowledge section of the tool.)")
        lines.append("  Note: MagicSchool field limits are ~75,000 words — far above any of our files.")
    else:
        lines.append("Knowledge: none — the contract is embedded in the Instructions file.")
    lines += [
        "",
        "Customize (suggested starting text):",
    ]
    for line in info["customize"]:
        lines.append(f"  {line}")
    lines += [
        "",
        "Build steps:",
        "  1. In MagicSchool: My Creations → + Create Tool → Configure.",
        "  2. Enter the suggested Tool Name and Tool Description above.",
        "  3. In Instructions: upload the instructions file (or paste it).",
    ]
    if info["knowledge"]:
        lines.append("  4. In Knowledge: attach the knowledge file(s) listed above.")
        lines.append("  5. In Customize: paste the suggested text above and adapt it.")
        lines.append("  6. Save and Test — paste a sample request to confirm the output format.")
        lines.append("  7. Share the tool with your co-workers.")
    else:
        lines.append("  4. In Customize: paste the suggested text above and adapt it.")
        lines.append("  5. Save and Test — paste a sample request to confirm the output format.")
        lines.append("  6. Share the tool with your co-workers.")
    return "\n".join(lines) + "\n"


def _build_toolkit(toolkit_dir, target_dir, rubric_folders):
    os.makedirs(toolkit_dir, exist_ok=True)
    written = []

    for tool_name, info in _TOOLKIT_TOOLS.items():
        # Instructions file
        if info["file"] is not None:
            src_path = os.path.join(target_dir, info["file"])
            if os.path.isfile(src_path):
                instr_text = _read_text(src_path)
            else:
                continue
        else:
            instr_text = _make_essay_scorer_instructions()

        instr_filename = f"{tool_name} — INSTRUCTIONS.txt"
        instr_path = os.path.join(toolkit_dir, instr_filename)
        _write_text_if_missing(instr_path, instr_text)
        written.append(instr_path)

        # Setup file
        setup_filename = f"{tool_name} — SETUP.txt"
        setup_path = os.path.join(toolkit_dir, setup_filename)
        _write_text_if_missing(setup_path, _make_setup_text(tool_name, info, instr_filename))
        written.append(setup_path)

        # Knowledge source copies
        for i, src in enumerate(info["knowledge_sources"]):
            if os.path.isfile(src):
                dest_name = info["knowledge"][i] if i < len(info["knowledge"]) else os.path.basename(src)
                dest = os.path.join(toolkit_dir, dest_name)
                if not os.path.exists(dest):
                    import shutil
                    shutil.copy2(src, dest)
                written.append(dest)

    return written


def build_library(target_dir, rubric_folders=None):
    """Build the AI-TA library using the current rubric folders by default."""
    if rubric_folders is None:
        rubric_folders = runtime_paths.rubric_folders()
    os.makedirs(target_dir, exist_ok=True)
    written = _copy_tree_if_missing(DEFAULT_AI_TA_DIR, target_dir)

    files = {
        "START HERE - What is Canvas Expert.txt": _make_start_here_text(),
        "About This Folder.txt": _about_text(),
    }

    for filename, (kind, tag, contract_path) in CONTRACT_FILES.items():
        files[filename] = _make_authoring_text(kind, tag, contract_path)

    for folder in rubric_folders:
        if not os.path.isdir(folder):
            continue
        for path in sorted(os.listdir(folder)):
            if not path.lower().endswith(".txt"):
                continue
            full_path = os.path.join(folder, path)
            data, problems = rf.parse_file(full_path)
            if data is None or problems:
                continue
            safe_title = _sanitize_filename(str(data.get("title", "Rubric")))
            filename = f"Score with - {safe_title}.txt"
            files[filename] = _make_rubric_score_text(data)

    for filename, text in files.items():
        out_path = os.path.join(target_dir, filename)
        _write_text_if_missing(out_path, text)
        written.append(out_path)

    # Build MagicSchool Toolkit subfolder
    toolkit_dir = os.path.join(target_dir, "MagicSchool Toolkit")
    written.extend(_build_toolkit(toolkit_dir, target_dir, rubric_folders))

    return written
