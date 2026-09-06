"""QuizForge item -> Canvas New Quizzes API item.

One builder per QF type. Shapes and scoring_algorithm values were verified live
against the sandbox (see qf_materials/qf quiz examples/README.md). Rationales are
expected to be pre-merged onto each item as item["_rationale"] by the pusher.

STIMULUS / STIMULUS_END are NOT handled here — the pusher strips them and inlines
their HTML into the attached items' bodies before transform runs.
"""
import re
import uuid


def _u():
    return str(uuid.uuid4())


def _p(text):
    """Wrap bare text in <p>; leave existing HTML alone."""
    text = str(text)
    return text if text.strip().startswith("<") else f"<p>{text}</p>"


def _wrap(entry, position, points=1):
    return {"item": {"entry_type": "Item", "position": position,
                     "points_possible": points, "entry": entry}}


def _neutral_feedback(item):
    """For single-rationale types: rationale string -> feedback.neutral."""
    rat = item.get("_rationale") or {}
    text = rat.get("rationale")
    return {"neutral": _p(text)} if text else {}


# --------------------------------------------------------------------------- #
def _because(text, rationale, correct):
    """Compose the points-back norm: '"answer" is correct/wrong. <rationale>'.

    Returns an HTML <span> colored green (correct) or red (wrong) with a ✓/✗ glyph.
    The verdict and the answer text are added here; the authored rationale follows
    as its own sentences. An API-presentation detail, not a QuizForge-contract
    requirement. HTML in `text` (e.g. <em>) is preserved.

    The verdict is a complete sentence rather than a trailing "because" clause: a
    rationale is now two sentences (a concept sentence, then a sentence tying it to
    this choice), and "is correct because Each HTML element has one job..." does not
    read as English. Keeping them as separate sentences composes with both shapes.
    """
    verb = "is correct" if correct else "is wrong"
    reason = (rationale or "").strip()
    color = "#1a6b1a" if correct else "#a50000"
    glyph = "✓" if correct else "✗"
    stmt = f'"{text}" {verb}.' + (f" {reason}" if reason else "")
    return f'<span style="color:{color}">{glyph} {stmt}</span>'


def t_mc(item, pos):
    rat = {c["id"]: c.get("rationale", "")
           for c in (item.get("_rationale") or {}).get("choices", [])}
    choices, idmap, correct_qid = [], {}, None
    for i, c in enumerate(item["choices"], 1):
        cu = _u()
        idmap[c["id"]] = cu
        choices.append({"id": cu, "position": i, "item_body": _p(c["text"])})
        if c.get("correct"):
            correct_qid = c["id"]
    correct_text = next(c["text"] for c in item["choices"] if c.get("correct"))
    correct_stmt = _because(correct_text, rat.get(correct_qid, ""), True)

    # Wrong choice -> "<correct> is correct because... <this> is wrong because..."
    # Correct choice -> just the correct statement.
    answer_feedback = {}
    for c in item["choices"]:
        cu = idmap[c["id"]]
        if c.get("correct"):
            answer_feedback[cu] = _p(correct_stmt)
        else:
            wrong_stmt = _because(c["text"], rat.get(c["id"], ""), False)
            answer_feedback[cu] = _p(f"{correct_stmt} {wrong_stmt}")
    entry = {
        "title": item.get("id", "MC"),
        "item_body": item["prompt"],
        "interaction_type_slug": "choice",
        "interaction_data": {"choices": choices},
        "scoring_data": {"value": idmap[correct_qid]},
        "scoring_algorithm": "Equivalence",
        "answer_feedback": answer_feedback,
    }
    return _wrap(entry, pos)


def t_ma(item, pos):
    rat = {c["id"]: c.get("rationale", "")
           for c in (item.get("_rationale") or {}).get("choices", [])}
    choices, idmap, correct = [], {}, []
    for i, c in enumerate(item["choices"], 1):
        cu = _u()
        idmap[c["id"]] = cu
        choices.append({"id": cu, "position": i, "item_body": _p(c["text"])})
        if c.get("correct"):
            correct.append(cu)
    # All correct statements, so a wrong selection still gets the full set.
    all_correct = " ".join(_because(c["text"], rat.get(c["id"], ""), True)
                           for c in item["choices"] if c.get("correct"))
    answer_feedback = {}
    for c in item["choices"]:
        cu = idmap[c["id"]]
        if c.get("correct"):
            answer_feedback[cu] = _p(_because(c["text"], rat.get(c["id"], ""), True))
        else:
            wrong_stmt = _because(c["text"], rat.get(c["id"], ""), False)
            answer_feedback[cu] = _p(f"{all_correct} {wrong_stmt}")
    entry = {
        "title": item.get("id", "MA"),
        "item_body": item["prompt"],
        "interaction_type_slug": "multi-answer",
        "interaction_data": {"choices": choices},
        "scoring_data": {"value": correct},
        "scoring_algorithm": "AllOrNothing",
        "answer_feedback": answer_feedback,
    }
    return _wrap(entry, pos)


def t_tf(item, pos):
    correct_text = "True" if bool(item["answer"]) else "False"
    rationale = (item.get("_rationale") or {}).get("rationale", "")
    feedback = {"neutral": _p(_because(correct_text, rationale, True))} if rationale \
        else {}
    entry = {
        "title": item.get("id", "TF"),
        "item_body": item["prompt"],
        "interaction_type_slug": "true-false",
        "interaction_data": {"true_choice": "True", "false_choice": "False"},
        "scoring_data": {"value": bool(item["answer"])},
        "scoring_algorithm": "Equivalence",
        "feedback": feedback,
    }
    return _wrap(entry, pos)


def t_numeric(item, pos):
    # Confirmed live: numeric needs scoring_algorithm "Numeric" and a value ARRAY
    # of response objects (with "Equivalence" the value array is rejected AND the
    # student's response won't display/grade).
    ev = item.get("evaluation") or {}
    mode = ev.get("mode", "exact")
    ans = str(item["answer"])
    rid = _u()
    if mode == "range":
        resp = {"id": rid, "type": "withinARange",
                "start": str(ev.get("min")), "end": str(ev.get("max"))}
    elif mode == "percent_margin":
        resp = {"id": rid, "type": "marginOfError", "value": ans,
                "margin": str(ev.get("value")), "margin_type": "percent"}
    elif mode == "absolute_margin":
        resp = {"id": rid, "type": "marginOfError", "value": ans,
                "margin": str(ev.get("value")), "margin_type": "absolute"}
    elif mode in ("decimal_places", "significant_digits"):
        ptype = "decimals" if mode == "decimal_places" else "significantDigits"
        resp = {"id": rid, "type": "preciseResponse", "value": ans,
                "precision": str(ev.get("value")), "precision_type": ptype}
    else:  # exact
        resp = {"id": rid, "type": "exactResponse", "value": ans}
    entry = {
        "title": item.get("id", "NUM"),
        "item_body": item["prompt"],
        "interaction_type_slug": "numeric",
        "interaction_data": {},
        "scoring_data": {"value": [resp]},
        "scoring_algorithm": "Numeric",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


def t_fitb(item, pos):
    # rich-fill-blank, single blank (all current fixtures are single-blank).
    tokens = re.findall(r"\[blank\d*\]", item["prompt"])
    if len(tokens) != 1:
        raise NotImplementedError(
            f"{item.get('id')}: only single-blank FITB is supported "
            f"(found {len(tokens)} blanks)")
    accept = item.get("accept", [])
    answer = accept[0] if accept else ""
    case_sensitive = bool(item.get("case_sensitive", False))
    mode = item.get("answer_mode", "open_entry")
    bid = _u()

    body = re.sub(r"\[blank\d*\]", "`Blank`", item["prompt"])

    if mode in ("wordbank", "dropdown"):
        atype = "wordbank" if mode == "wordbank" else "dropdown"
        word_bank = [{"id": _u(), "item_body": o} for o in item.get("options", [])]
        blanks = [{"id": bid, "answer_type": atype}]
    else:
        atype = "openEntry"
        word_bank = []
        blanks = [{"id": bid, "answer_type": atype}]

    entry = {
        "title": item.get("id", "FITB"),
        "item_body": body,
        "interaction_type_slug": "rich-fill-blank",
        "interaction_data": {
            "blanks": blanks,
            "word_bank_choices": word_bank,
            "reuse_word_bank_choices": bool(word_bank),
        },
        "scoring_data": {
            "value": [{
                "id": bid,
                "scoring_data": {
                    "value": answer,
                    "blank_text": answer,
                    "ignore_case": not case_sensitive,
                    "edit_distance": 1,   # server requires > 0
                },
                "scoring_algorithm": "TextCloseEnough",
            }],
            "working_item_body": body,
        },
        "scoring_algorithm": "MultipleMethods",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


def t_matching(item, pos):
    pairs = item["pairs"]
    distractors = list(item.get("distractors", []))
    questions, value, matches = [], {}, []
    answers = [p["right"] for p in pairs] + distractors
    for i, p in enumerate(pairs, 1):
        qid = str(10000 + i)
        questions.append({"id": qid, "item_body": p["left"]})
        value[qid] = p["right"]
        matches.append({"answer_body": p["right"], "question_id": qid,
                        "question_body": p["left"]})
    entry = {
        "title": item.get("id", "MATCH"),
        "item_body": item["prompt"],
        "interaction_type_slug": "matching",
        "interaction_data": {"answers": answers, "questions": questions},
        "scoring_data": {"value": value,
                         "edit_data": {"matches": matches, "distractors": distractors}},
        "scoring_algorithm": "DeepEquals",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


def t_ordering(item, pos):
    choices, order = {}, []
    for entry_text in item["items"]:
        cu = _u()
        choices[cu] = {"id": cu, "item_body": str(entry_text)}  # plain text
        order.append(cu)
    entry = {
        "title": item.get("id", "ORDER"),
        "item_body": item.get("prompt") or _p(item.get("header", "Put in order")),
        "interaction_type_slug": "ordering",
        "interaction_data": {"choices": choices},
        "scoring_data": {"value": order},
        "scoring_algorithm": "DeepEquals",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


def t_categorization(item, pos):
    categories, cat_order, label_to_cat = {}, [], {}
    for label in item["categories"]:
        cu = _u()
        categories[cu] = {"id": cu, "item_body": label}
        cat_order.append(cu)
        label_to_cat[label] = cu
    distractors, cat_items = {}, {cu: [] for cu in cat_order}
    for it in item["items"]:
        iu = _u()
        distractors[iu] = {"id": iu, "item_body": it["label"]}
        cat_items[label_to_cat[it["category"]]].append(iu)
    for d in item.get("distractors", []):       # unsortable extras
        iu = _u()
        distractors[iu] = {"id": iu, "item_body": d}
    value = [{"id": cu, "scoring_data": {"value": cat_items[cu]},
              "scoring_algorithm": "AllOrNothing"} for cu in cat_order]
    entry = {
        "title": item.get("id", "CAT"),
        "item_body": item["prompt"],
        "interaction_type_slug": "categorization",
        "interaction_data": {"categories": categories, "distractors": distractors,
                             "category_order": cat_order},
        "scoring_data": {"value": value, "score_method": "all_or_nothing"},
        "scoring_algorithm": "Categorization",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


def t_essay(item, pos):
    entry = {
        "title": item.get("id", "ESSAY"),
        "item_body": item["prompt"],
        "interaction_type_slug": "essay",
        "interaction_data": {"rce": True, "word_count": True, "file_upload": False},
        "scoring_data": {"value": item.get("rubric_hint", "")},
        "scoring_algorithm": "None",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


def t_fileupload(item, pos):
    fmts = ",".join(item.get("accepted_formats", []))
    entry = {
        "title": item.get("id", "UPLOAD"),
        "item_body": item["prompt"],
        "interaction_type_slug": "file-upload",
        "interaction_data": {"files_count": "1", "restrict_count": True},
        "properties": {"allowed_types": fmts, "restrict_types": bool(fmts)},
        "scoring_data": {"value": ""},
        "scoring_algorithm": "None",
        "feedback": _neutral_feedback(item),
    }
    return _wrap(entry, pos)


BUILDERS = {
    "MC": t_mc, "MA": t_ma, "TF": t_tf, "NUMERICAL": t_numeric, "FITB": t_fitb,
    "MATCHING": t_matching, "ORDERING": t_ordering, "CATEGORIZATION": t_categorization,
    "ESSAY": t_essay, "FILEUPLOAD": t_fileupload,
}


def build_item(qf_item, position):
    t = qf_item["type"]
    if t not in BUILDERS:
        raise ValueError(f"No transformer for QF type {t!r}")
    return BUILDERS[t](qf_item, position)
