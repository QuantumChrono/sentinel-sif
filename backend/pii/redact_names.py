"""Redact likely personal names from report text before it is stored or displayed.

RULE-BASED, NOT AN NLP MODEL. Two patterns catch a name:
1. An honorific (Mr/Mrs/Ms/Dr/Shri/Smt/Sri) followed by one or two capitalized words.
2. A capitalized word (or two in a row) that is NOT the first word of a sentence and NOT in
   `KNOWN_NON_NAMES` (site names, common sentence-openers, days, months).

WHAT THIS DOES NOT DO, STATED RATHER THAN HIDDEN. It is not a named-entity model: an
unfamiliar proper noun this list does not know (a place, a brand, an equipment model number)
can be indistinguishable from a name and will be over-redacted. A name that IS the first word
of its sentence is currently invisible to rule 2 - only rule 1 (the honorific case) catches
that. Treat this as reducing exposure, not eliminating it.
"""

import re

HONORIFICS = ("Mr", "Mrs", "Ms", "Mx", "Dr", "Shri", "Smt", "Sri")

# Capitalized words that are not names. Kept short, explicit, and local to this file rather
# than importing another lane's internal vocabulary (e.g. precursor_ner.py's SITE_NAMES) -
# see AUDIT.md if this list needs to grow.
KNOWN_NON_NAMES = {
    "Duliajan", "Naharkatiya", "Moran", "Baghjan", "Makum", "Hapjan", "Tanot", "Ramgarh",
    "The", "A", "An", "On", "At", "During", "While", "After", "Before", "He", "She", "They",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
}

_HONORIFIC_NAME = re.compile(
    rf"\b((?:{'|'.join(HONORIFICS)})\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
)

# A capitalized word (or two in a row), preceded by a lowercase letter or a comma and a space
# - i.e. not sentence-initial, where capitalization alone proves nothing about it being a name.
_MID_SENTENCE_CAP = re.compile(r"(?<=[a-z,]\s)([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b")


def _redact_honorific(match: re.Match) -> str:
    return f"{match.group(1)} [REDACTED]"


def _redact_if_unknown(match: re.Match) -> str:
    candidate = match.group(1)
    first_word = candidate.split()[0]
    if first_word in KNOWN_NON_NAMES:
        return candidate
    return "[REDACTED]"


def redact_names(text: str) -> str:
    """Return `text` with likely personal names replaced by `[REDACTED]`.

    Never raises: a regex failure here degrades to returning the original text, the same
    contract `preprocessing.clean_report` uses, since this runs in the same synchronous
    request path and a crash here must not take the whole submission down with it.
    """
    try:
        redacted = _HONORIFIC_NAME.sub(_redact_honorific, text)
        redacted = _MID_SENTENCE_CAP.sub(_redact_if_unknown, redacted)
        return redacted
    except Exception:
        return text