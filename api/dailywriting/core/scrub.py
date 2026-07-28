"""Name removal for student writing (INV-7).

Names appear inside student writing. A kid writes about his brother, or names
a classmate in a paragraph about the assigned reading. Canvas Expert's
existing scrubber (`api.feedback_scrub`) is a high-precision denylist built
from the roster vault, which is exactly right for the classmate and blind to
the brother, because the brother is not on any roster.

So this module runs two passes, in this order:

  1. Roster pass. Delegates to `api.feedback_scrub`, which maps every real
     name, nickname, and id in the vault to that student's stable pseudonym.
     Authoritative, and it always wins.
  2. General pass. Heuristic capitalized-token detection for every name the
     roster does not know. Replaces with `NAME_PLACEHOLDER` and records a
     finding so the teacher digest can show what was touched.

The general pass exempts three sets, in order of how much they are trusted:
the pseudonyms the roster pass just introduced (redacting the safe substitute
would be absurd), the assignment's own provided text (a capitalized name in
the prompt or source passage is course content, not a private disclosure),
and the teacher's enabled literary packs (quoting Ponyboy is the assignment).
A roster name is never exempt: privacy wins over a literary match, which is
the ordering `api.feedback_scrub` already established.

The pass order matters and is not interchangeable. `NAME_PLACEHOLDER`
contains word characters, so it is only safe because the roster pass, whose
rules are `\\b`-bounded and case-insensitive, has already finished by the time
the placeholder exists. The general pass cannot match its own output, because
every candidate needs a capital initial.

Scrubbing happens at ingest, before segmentation, and the unscrubbed text is
never persisted. That ordering is the whole defence: a scrub bolted on later
has already been outrun by the spans quoted out of the text.

Pure stdlib apart from two optional Canvas Expert lookups, both lazily
imported so this module stays offline-testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from api.dailywriting.core.models import ScrubFinding

# Readable in a teacher's digest, unlike an opaque token. Safe against
# re-matching because every candidate pattern requires a capital initial.
NAME_PLACEHOLDER = "[name]"

# Candidate shape: a capitalised word, optionally hyphenated ("Two-Bit").
# Deliberately excludes single letters ("I") and all-caps acronyms ("STAAR").
_CANDIDATE = re.compile(r"\b[A-Z][a-z]+(?:-[A-Z][a-z]+)*\b")

# A capitalised token straight after one of these is a person, even when the
# token itself sits in the ordinary-word lexicon. "My friend Grace" beats the
# fact that "grace" is a common word.
_PERSON_CUES = frozenset({
    "brother", "sister", "mom", "mother", "dad", "father", "stepdad",
    "stepmom", "stepbrother", "stepsister", "friend", "bestfriend", "cousin",
    "uncle", "aunt", "grandma", "grandmother", "grandpa", "grandfather",
    "neighbor", "neighbour", "teammate", "classmate", "partner", "buddy",
    "boyfriend", "girlfriend", "babysitter", "nephew", "niece", "twin",
    "coach", "teacher", "principal", "counselor", "nurse", "officer",
    "named", "called",
})

# Titles: the following token is a surname.
_TITLES = frozenset({
    "mr", "mrs", "ms", "miss", "dr", "coach", "principal", "officer",
    "sergeant", "captain", "professor", "pastor", "sir", "madam",
})

# Ordinary words that arrive capitalised, chiefly at the start of a sentence.
# Not exhaustive and not meant to be: anything missing gets redacted and
# flagged, which is the failure direction the teacher can actually see.
_NON_NAME_WORDS = frozenset({
    # determiners, pronouns, conjunctions, prepositions
    "the", "a", "an", "and", "but", "or", "nor", "for", "so", "yet",
    "if", "then", "than", "that", "this", "these", "those", "there", "their",
    "they", "them", "he", "she", "it", "its", "his", "her", "hers", "him",
    "we", "us", "our", "ours", "you", "your", "yours", "my", "mine", "me",
    "who", "whom", "whose", "which", "what", "when", "where", "why", "how",
    "while", "whenever", "wherever", "whereas", "although", "though",
    "because", "since", "unless", "until", "after", "before", "during",
    "about", "above", "across", "against", "along", "among", "around", "at",
    "behind", "below", "beneath", "beside", "besides", "between", "beyond",
    "by", "despite", "down", "from", "in", "inside", "into", "like", "near",
    "of", "off", "on", "onto", "out", "outside", "over", "past", "through",
    "throughout", "to", "toward", "towards", "under", "up", "upon", "with",
    "within", "without",
    # common sentence openers and verbs
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "done", "have", "has", "had", "can", "could", "will", "would",
    "shall", "should", "may", "might", "must", "let", "lets",
    "according", "also", "always", "another", "any", "anyone", "anything",
    "both", "each", "either", "even", "every", "everyone", "everybody",
    "everything", "few", "first", "second", "third", "finally", "however",
    "instead", "just", "many", "more", "most", "much", "neither", "never",
    "next", "no", "nobody", "none", "not", "nothing", "now", "once", "one",
    "only", "other", "others", "overall", "perhaps", "really", "same",
    "several", "similarly", "some", "someone", "something", "sometimes",
    "still", "such", "sure", "then", "therefore", "thus", "together", "too",
    "usually", "very", "well", "whether", "yes",
    # words a 7th grader opens an argument with
    "adults", "author", "authors", "book", "books", "character", "characters",
    "chapter", "class", "classes", "college", "kid", "kids", "child",
    "children", "essay", "evidence", "example", "family", "families",
    "grade", "grades", "homework", "however", "human", "humans", "life",
    "money", "narrator", "page", "paragraph", "parents", "people", "person",
    "phone", "phones", "quote", "reader", "readers", "reading", "reasons",
    "school", "schools", "science", "society", "sports", "story", "stories",
    "student", "students", "teachers", "teens", "teenagers", "test", "tests",
    "text", "time", "today", "writing", "world", "year", "years", "youth",
    # calendar and time
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "yesterday", "today", "tomorrow", "tonight", "morning", "afternoon",
    "evening", "night", "week", "weekend", "month", "winter", "spring",
    "autumn", "recently", "lately", "later", "earlier", "meanwhile",
    "afterward", "afterwards", "eventually", "suddenly", "immediately",
    # sentence-opening adverbs
    "actually", "basically", "honestly", "personally", "obviously",
    "clearly", "unfortunately", "luckily", "hopefully", "especially",
    "generally", "mostly", "probably", "definitely", "certainly", "surely",
    "maybe", "often", "rarely", "sadly", "truthfully", "frankly",
    "furthermore", "moreover", "nevertheless", "nonetheless", "regardless",
    "meanwhile", "otherwise", "likewise", "consequently", "additionally",
    # places, languages, subjects that arrive capitalised legitimately
    "america", "american", "americans", "english", "spanish", "texas",
    "texan", "earth", "internet", "google", "canvas", "chromebook",
    "youtube", "christmas", "thanksgiving", "halloween",
})


def _ambiguous_name_words() -> frozenset[str]:
    """Words that are ordinary English and also common given names.

    Reuses `api.feedback_scrub.COMMON_WORDS`, which the repository already
    curates for exactly this ambiguity ("Grace", "Will", "Rose", "Mark").
    Duplicating that judgement here would give two lists that drift apart.

    These are redacted only mid-sentence. Sentence-initial capitalisation is
    forced by grammar and so carries no evidence that the word is a name;
    capitalisation in the middle of a sentence does.
    """
    from api.feedback_scrub import COMMON_WORDS
    return frozenset(COMMON_WORDS)


def _sentence_initial(text: str, index: int) -> bool:
    """Is the token at `index` the first word of a sentence or a line?"""
    head = text[:index].rstrip(" \t\"'“”([")
    if not head:
        return True
    return head[-1] in ".!?\n"


class ScrubLeakError(RuntimeError):
    """A real roster name survived scrubbing. Never store the text."""


class UnsanitizedOutboundError(ValueError):
    """An external-model boundary was given text that never passed scrub."""


@dataclass(frozen=True)
class ScrubResult:
    text: str
    findings: list[ScrubFinding]

    @property
    def general_name_hits(self) -> int:
        """Non-roster names removed. These are the ones worth human eyes."""
        return sum(1 for f in self.findings if f.kind == "general_name")


@dataclass(frozen=True)
class ModelReadyText:
    """A scrubbed string approved for a future external-model call.

    No client is built in this substrate.  This small typed boundary is the
    only representation that a later client may accept, so raw strings are
    rejected before they can become an outbound payload.
    """

    text: str


def load_protected_names() -> set[str]:
    """Teacher-enabled literary packs plus custom protected names, lowercased.

    Returns an empty set when there is no workspace to read, which is the
    normal state under test. Empty means the general pass redacts literary
    names too, which is the safe direction to fail.
    """
    try:
        from api.webui.config import protected_names
        return set(protected_names.active_protected_names())
    except Exception:
        return set()


def build_roster_map(vault) -> list[tuple]:
    """Compiled roster replacement rules for `vault`, longest match first."""
    from api import feedback_scrub
    return feedback_scrub.build_replacement_map(
        vault.entries(), load_protected_names()
    )


def corpus_allowlist(*texts: str | Iterable[str]) -> set[str]:
    """Capitalised tokens appearing in provided text, lowercased.

    A name in the prompt or the source passage is the assignment, not a
    student's private disclosure. High precision, because the authoring record
    holds this text exactly.
    """
    allow: set[str] = set()
    for item in texts:
        if item is None:
            continue
        chunks: Sequence[str]
        chunks = [item] if isinstance(item, str) else list(item)
        for chunk in chunks:
            for match in _CANDIDATE.finditer(chunk or ""):
                token = match.group()
                allow.add(token.lower())
                for part in token.split("-"):
                    allow.add(part.lower())
    return allow


def _replacement_tokens(roster_map: list[tuple]) -> set[str]:
    """Lowercased tokens of every pseudonym the roster pass can introduce."""
    tokens: set[str] = set()
    for _pattern, replacement in roster_map or []:
        for token in re.findall(r"[A-Za-z]+", replacement or ""):
            tokens.add(token.lower())
    return tokens


def _preceding_word(text: str, index: int) -> str:
    """Lowercased word ending just before `index`, ignoring punctuation."""
    head = text[:index].rstrip()
    head = head.rstrip(".,;:!?\"'()[]-")
    match = re.search(r"([A-Za-z]+)\s*$", head)
    return match.group(1).lower() if match else ""


def _locate_findings(text: str, needle: str, kind: str) -> list[ScrubFinding]:
    """Findings for every occurrence of `needle` in the final text.

    `detail` stays empty on purpose: a finding is written to the same private
    store as everything else, and recording the value that was removed would
    reintroduce exactly what the removal took out.
    """
    findings: list[ScrubFinding] = []
    if not needle:
        return findings
    start = text.find(needle)
    while start != -1:
        findings.append(ScrubFinding(
            kind=kind,  # type: ignore[arg-type]
            replacement=needle,
            span_start=start,
            span_end=start + len(needle),
        ))
        start = text.find(needle, start + len(needle))
    return findings


def _roster_pass(text: str, roster_map: list[tuple]) -> tuple[str, list[ScrubFinding]]:
    """Apply the vault's rules, then locate what landed."""
    from api import feedback_scrub

    if not roster_map:
        return text, []
    scrubbed = feedback_scrub.scrub_text(text, roster_map)
    if scrubbed == text:
        return scrubbed, []

    findings: list[ScrubFinding] = []
    findings.extend(_locate_findings(
        scrubbed, feedback_scrub.ID_PLACEHOLDER, "roster_id"))
    # One finding per pseudonym token now present that was not there before,
    # which is the closest honest account of "a roster name was here".
    for replacement in sorted({r for _p, r in roster_map
                               if r and r != feedback_scrub.ID_PLACEHOLDER}):
        added = scrubbed.count(replacement) - text.count(replacement)
        if added <= 0:
            continue
        for finding in _locate_findings(scrubbed, replacement, "roster_name")[:added]:
            findings.append(finding)
    return scrubbed, findings


def _general_pass(
    text: str,
    *,
    exempt: set[str],
) -> tuple[str, list[ScrubFinding]]:
    """Redact capitalised tokens that look like people and are not exempt.

    Single left-to-right pass over the original string, building the output as
    we go, so recorded offsets are real offsets in the returned text.
    """
    out: list[str] = []
    findings: list[ScrubFinding] = []
    cursor = 0
    written = 0  # length of "".join(out), tracked so offsets stay O(n)
    ambiguous = _ambiguous_name_words()

    for match in _CANDIDATE.finditer(text):
        token = match.group()
        lowered = token.lower()
        parts = [p.lower() for p in token.split("-")]

        cue = _preceding_word(text, match.start())
        forced = cue in _PERSON_CUES or cue in _TITLES

        if not forced:
            if lowered in exempt or any(p in exempt for p in parts):
                continue
            if (lowered in ambiguous
                    and not _sentence_initial(text, match.start())):
                # ``Will`` and friends are ordinary words at a sentence
                # opening, but their capitalisation in the middle of a
                # sentence is evidence of a name.  This check must precede
                # the general ordinary-word lexicon, which also contains
                # "will" as a modal verb.
                pass
            elif lowered in _NON_NAME_WORDS:
                continue
            elif (lowered in ambiguous
                  and _sentence_initial(text, match.start())):
                # "Grace is what the author means" opens a sentence, so the
                # capital proves nothing. "I told Grace" does not.
                continue
            # A capitalised word we have no lexicon entry for is treated as a
            # name. Sentence-initial words reach here too, which is why the
            # lexicon above carries the common openers.
        elif lowered in exempt:
            # Even a cue does not override the assignment's own text or the
            # teacher's literary packs: "my friend Ponyboy" in an Outsiders
            # essay is a character, not a classmate.
            continue

        lead = text[cursor:match.start()]
        out.append(lead)
        written += len(lead)
        out.append(NAME_PLACEHOLDER)
        findings.append(ScrubFinding(
            kind="general_name",
            replacement=NAME_PLACEHOLDER,
            span_start=written,
            span_end=written + len(NAME_PLACEHOLDER),
        ))
        written += len(NAME_PLACEHOLDER)
        cursor = match.end()

    out.append(text[cursor:])
    return "".join(out), findings


def scrub_writing(
    text: str,
    *,
    vault=None,
    roster_map: list[tuple] | None = None,
    protected: set[str] | None = None,
    assignment_corpus: Iterable[str] = (),
) -> ScrubResult:
    """Scrub student writing for storage. Call this at ingest, before anything
    reads or quotes the text.

    Supply either `vault` or a prebuilt `roster_map`; pass neither and only
    the general pass runs, which is the right behaviour for a fixture with no
    roster but never the right behaviour in production.
    """
    if text is None:
        return ScrubResult(text="", findings=[])

    rules = roster_map
    if rules is None and vault is not None:
        rules = build_roster_map(vault)
    rules = rules or []

    scrubbed, findings = _roster_pass(text, rules)

    exempt: set[str] = set()
    exempt |= _replacement_tokens(rules)
    exempt |= corpus_allowlist(assignment_corpus)
    exempt |= (protected if protected is not None else load_protected_names())

    scrubbed, general_findings = _general_pass(scrubbed, exempt=exempt)
    findings.extend(general_findings)

    return ScrubResult(text=scrubbed, findings=findings)


def assert_clean_for_storage(text: str, vault=None) -> None:
    """Raise if any real roster name survived. Call before persisting a span.

    Cheap, and it is the difference between a bug and a disclosure.
    """
    if vault is None or not text:
        return
    from api import feedback_scrub
    survivors = feedback_scrub.verify_clean(text, vault)
    if survivors:
        raise ScrubLeakError(
            f"{len(survivors)} real name(s) survived scrubbing; refusing to "
            "store this text. Check the vault's nickname coverage for this "
            "section."
        )


def model_ready_text(
    scrubbed: ScrubResult,
    *,
    pseudonyms: Iterable[str],
    vault=None,
) -> ModelReadyText:
    """Create the only future-model input representation from scrub output.

    A raw ``str`` is refused even if it happens not to contain a name: callers
    must establish the scrub-before-any-downstream-work ordering explicitly.
    Tenant-side records may retain the vault's safe pseudonyms, but an
    external-model payload may not, so the caller must supply its section's
    pseudonyms and this boundary removes them. The roster survivor check
    remains useful when a vault is available.
    """
    if not isinstance(scrubbed, ScrubResult):
        raise UnsanitizedOutboundError(
            "outbound text must be a ScrubResult from scrub_writing(), not a "
            "raw string"
        )
    known_pseudonyms = {p.strip() for p in pseudonyms if p and p.strip()}
    if not known_pseudonyms:
        raise UnsanitizedOutboundError(
            "outbound text requires the section pseudonyms so none can leave "
            "the tenant"
        )
    text = scrubbed.text
    for pseudonym in sorted(known_pseudonyms, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(pseudonym)}\b", NAME_PLACEHOLDER,
                      text, flags=re.IGNORECASE)
    assert_clean_for_storage(text, vault)
    return ModelReadyText(text=text)
