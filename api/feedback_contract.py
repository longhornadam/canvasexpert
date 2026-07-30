"""Feedback tools contract and prompt helpers.

These helpers define the teacher-facing scoring instructions and persona signoff
behavior used by the feedback tools pipeline and PowerGrader packet builders.
"""
import json
import os
import re

from api.nq_report import constructed_responses, html_to_text, parse_student_analysis_file
from api.feedback_vault import Vault

CONTRACT_VERSION = "1.0"
_REVIEW_NOTE = ("Pseudonymized for privacy. Review the response text for any "
                "self-identifying details (names, places) before sending to an LLM.")


def _safe(name, max_len=80):
    s = re.sub(r'[^\w\- ]+', "", (name or "").strip())
    return (re.sub(r'\s+', " ", s)[:max_len] or "quiz").strip()


def persona_signoff(persona: dict | None = None,
                    ai_ta_name: str = "your teaching assistant") -> str:
    """Return the persona's student-visible signoff, if that persona wants one."""
    persona = persona or {}
    name = str(persona.get("name") or ai_ta_name or "your teaching assistant").strip()
    policy = str(persona.get("signoff_policy") or "").strip().lower()
    if not policy:
        return ""
    if policy in {"none", "off", "no_signoff"}:
        return ""
    template = str(persona.get("signoff_text") or "").strip()
    if not template and policy == "ai_disclosure":
        template = "Drafted by {name} (AI), reviewed by your teacher."
    if not template:
        return ""
    return template.replace("{name}", name)


def build_contract_text(ai_ta_name: str = "your teaching assistant",
                        rubric_text: str = "",
                        persona: dict | None = None) -> str:
    """Instructions the teacher pastes into their LLM alongside the bundle.

    When `rubric_text` is provided it is inlined below so the file is self-contained
    (prompt context lives in the bundle; the rubric travels here) - no separate
    attach step. When omitted, the older "attach the rubric as Knowledge" wording
    is used (the parked NQ / OpenRouter lanes supply the rubric separately).
    Extends the Essay Scorer skill: keyed batch output for automatic
    re-identification. Student-facing signoff is persona-controlled, not part of
    the scoring contract.
    """
    persona = persona or {}
    ai_ta_name = str(persona.get("name") or ai_ta_name or "your teaching assistant").strip()
    signoff = persona_signoff(persona, ai_ta_name)
    signoff_clause = ""
    disclosure_example = ""
    disclosure_rule = "- `disclosure` is optional metadata; leave it empty if the persona has no signoff."
    if signoff:
        signoff_clause = (
            "\n\nThis persona uses this student-visible signoff. End each `feedback` "
            f"value with it exactly once:\n{signoff}"
        )
        disclosure_example = f',\n    "disclosure": "{signoff}"'
        disclosure_rule = "- If `disclosure` is present, copy the persona signoff exactly."
    if rubric_text.strip():
        rubric_clause = ("The scoring rubric is included at the bottom of this file "
                         "— score strictly by it, do not invent criteria.")
        rubric_block = f"\n\n--- RUBRIC (score strictly by this) ---\n{rubric_text.strip()}\n"
    else:
        rubric_clause = ("A RubricForge rubric is attached as Knowledge — score "
                         "strictly by it, do not invent criteria.")
        rubric_block = ""
    return f"""You are {ai_ta_name}, a teaching assistant helping a real teacher
score student writing and draft feedback. {rubric_clause}

You will receive a JSON bundle of pseudonymized responses. For EACH response return
one result object. Output ONLY a JSON array, each element exactly:

  {{"pseudonym": "<copy>", "item_id": "<copy>", "score": <number>,
    "feedback": "<actionable, kind, rubric-anchored feedback for the student>"{disclosure_example}}}

Rules:
- Copy `pseudonym` and `item_id` back EXACTLY so results can be matched.
- If the bundle includes `shared_context`, use that assignment/source material
  when scoring every response. Do not ask for missing source material unless it
  is truly impossible to score without it.
- Quote briefly from the response to justify the score.
- Do not identify students.
- Do not invent a separate signature or disclosure beyond the selected persona.
{disclosure_rule}
- Use the full score range; `possible` gives each item's maximum.{signoff_clause}{rubric_block}"""
