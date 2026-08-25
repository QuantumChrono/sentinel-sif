"""Precursor entity extraction. One public function, `extract_precursors`.

THE SIGNATURE IS FROZEN (`STAGES.md` § FROZEN files):
`extract_precursors(text) -> list[(entity_type, entity_text, span_start, span_end)]`.
Only the body changes when the spaCy entity ruler replaces it in Block 8.

THE SPAN INVARIANT IS THE WHOLE POINT OF THIS FILE. `text[span_start:span_end] == entity_text`
holds for every tuple returned, and it holds BY CONSTRUCTION rather than by care: `entity_text`
is never assembled or copied from a pattern, it is always sliced back out of the exact string
that was passed in (see `_span`). This is the explainability mechanism in `PRD.md` § ML pipeline
detail - the Report Detail view highlights `cleaned_text` directly from these offsets, so an
off-by-one is visible on a projector. A design where the text and the offsets are produced
independently can drift; this one cannot.

SPANS NEVER OVERLAP. The highlighter wraps each span in its own element, so two overlapping
spans would produce nested or interleaved markup and render wrong. `_resolve_overlaps` keeps
the longest match at each position and drops anything crossing it.

BARRIER_FAILURE IS SPARSE ON PURPOSE. `DECISIONS.md` ("Barrier spans sourced by entailment
only") establishes that OSHA narratives record what happened, not which control was missing -
a word-boundary scan of all 20 source narratives found ZERO naming a failed control, and 1 of
20 sample rows carries a barrier span. Returning three of the four entity types is therefore
the NORMAL case here, not a failure, and this module must never invent a barrier to fill the
gap: a fabricated cause is the worst output a safety model can produce.
"""

import re

MODEL_VERSION = "interim-keyword-0.1"

# INTERIM_LANE_A - everything below is interim scaffolding. Delete the bodies, keep the
# signature. Owner: Lane A, Day 2 (DECISIONS.md, "Interim inference implementations behind
# frozen signatures").
#
# PROVENANCE. The vocabulary below is taken from the entity spans the dataset actually carries
# in `data/sample/localized.jsonl` (`precursor_activity` / `_location` / `_equipment` /
# `_barrier_failure`) plus the equipment and site vocabulary already curated in
# `preprocessing/oil_acronyms.py` DOMAIN_WORDS. It is not a general-purpose English NER.
#
# NOTE ON WHAT THESE PATTERNS SEE. Inference runs on `cleaned_text`, i.e. after acronym
# expansion. `dg set` has already become "diesel generator set" and `ppe` "personal protective
# equipment" by the time this module runs, so the patterns match the EXPANDED forms.

# A phrase continues across ordinary words but stops dead at a clause boundary. Without this,
# "welding a flange when the spark fell" swallows the whole sentence into one activity span.
CLAUSE_STOP = (
    "and", "but", "when", "while", "then", "because", "so", "which", "that", "after",
    "before", "as", "if", "though", "however", "therefore", "was", "were", "is", "are",
)
_STOP = "|".join(CLAUSE_STOP)

# Up to 5 following words, none of them a clause boundary. Bounded so a pattern cannot run to
# the end of a long report.
_TAIL = rf"(?:\s+(?!(?:{_STOP})\b)[a-z0-9][a-z0-9-]*){{0,5}}"

# --- activity: what the person was doing -----------------------------------------------
# Gerunds and past-progressive verbs, from the sample spans ("checking tension on the motor
# belt", "welding a wellhead flange", "walking from the drill floor to the crew locker").
ACTIVITY_VERBS = (
    "welding", "cutting", "grinding", "drilling", "driving", "lifting", "hoisting", "slinging",
    "rigging", "loading", "unloading", "moving", "carrying", "stacking", "climbing",
    "descending", "walking", "erecting", "dismantling", "installing", "removing", "replacing",
    "repairing", "servicing", "cleaning", "washing", "greasing", "lubricating", "inspecting",
    "checking", "testing", "adjusting", "tightening", "loosening", "opening", "closing",
    "operating", "handling", "connecting", "disconnecting", "entering", "digging",
    "excavating", "painting", "spraying", "pouring", "filling", "draining", "aligning",
    "realigning", "positioning", "swabbing", "pigging", "tripping out", "running in",
)
ACTIVITY_PATTERNS = tuple(
    re.compile(rf"\b{verb}{_TAIL}", re.IGNORECASE) for verb in ACTIVITY_VERBS
)

# --- location: where it happened -------------------------------------------------------
# The 8 seeded site names in `schema.sql`, each optionally followed by its site-type word.
SITE_NAMES = ("Duliajan", "Naharkatiya", "Moran", "Baghjan", "Makum", "Hapjan", "Tanot",
              "Ramgarh")
SITE_TYPES = ("field", "oilfield", "site", "rig", "installation", "plant", "terminal", "depot",
              "area", "block")

# Place nouns inside a facility, with an optional single modifier ("concrete walkway",
# "metal walkway", "steep earthen slope" - all real sample spans).
PLACE_NOUNS = (
    "drill floor", "rig floor", "derrick", "monkeyboard", "monkey board", "mast", "substructure",
    "cellar pit", "cellar", "mud pit", "shale shaker", "pump house", "pumphouse", "generator room",
    "control room", "workshop", "store", "warehouse", "yard", "laydown area", "pipe yard",
    "walkway", "gangway", "catwalk", "stairway", "staircase", "ladder", "platform", "scaffold",
    "gantry", "roof", "trench", "excavation", "pit", "sump", "tank", "vessel", "separator",
    "wellhead", "well pad", "group gathering station", "oil collecting station", "flare pit",
    "access road", "approach road", "camp", "kitchen", "locker", "gate", "slope", "embankment",
)
PLACE_MODIFIERS = ("concrete", "metal", "steel", "wooden", "earthen", "steep", "uneven", "wet",
                   "muddy", "upper", "lower", "main", "temporary", "makeshift")

# --- equipment: what was involved ------------------------------------------------------
EQUIPMENT_NOUNS = (
    "blowout preventer", "drawworks", "top drive", "topdrive", "kelly", "swivel", "rotary table",
    "drill pipe", "drill collar", "casing", "tubing", "elevator", "elevators", "slips", "tong",
    "tongs", "wireline", "coiled tubing", "sucker rod pump", "electrical submersible pump",
    "diesel generator set", "diesel generator", "generator", "compressor", "pump", "motor",
    "engine", "gearbox", "belt", "chain", "sprocket", "shaft", "coupling", "flywheel",
    "crane", "hoist", "winch", "chain block", "forklift", "trolley", "cart", "sling", "shackle",
    "wire rope", "hook", "spreader beam", "jack", "manifold", "valve", "flange", "gasket",
    "pipeline", "flowline", "hose", "gas cylinder", "cylinder", "drum", "barrel",
    "pressure washer", "grinder", "welding machine", "cutting torch", "gas torch", "hammer",
    "spanner", "wrench", "control panel", "switchgear", "breaker", "transformer", "cable",
    "vehicle", "truck", "tractor", "trailer", "tanker", "jeep", "bus", "ambulance",
    "personal protective equipment", "helmet", "harness", "lanyard", "fall arrest",
    "self contained breathing apparatus", "gas detector", "scaffold", "pipe rack", "tool rack",
)
EQUIPMENT_MODIFIERS = ("electric", "electrical", "hydraulic", "pneumatic", "diesel", "portable",
                       "rotating", "high pressure", "heavy", "mobile", "overhead", "augur",
                       "auger", "belt", "angle", "bench")

# --- barrier_failure: the control that was absent or defeated --------------------------
# Entailment-shaped phrases only (DECISIONS.md). Each names a specific control together with
# its absence or defeat - never a bare hazard word, and never inferred from the outcome.
BARRIER_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bwithout (?:a |the |any )?(?:permit|permit to work|authorisation|authorization|"
    r"job safety analysis|isolation|lockout|lock out|lockout tagout|guard|harness|"
    r"personal protective equipment|helmet|gas test|supervision|clearance)\w*",
    r"\bno (?:permit|permit to work|isolation|lockout|guard|harness|gas test|barricade|"
    r"exclusion zone|edge protection)\b",
    r"\b(?:guard|interlock|alarm|trip|limit switch|safety device|protective device)s? "
    r"(?:was|were)? ?(?:not |never )?(?:removed|missing|absent|bypassed|defeated|disabled|"
    r"overridden|inoperative|tied down)\b",
    r"\b(?:not |never )(?:isolated|locked out|tagged out|de-?energised|de-?energized|"
    r"barricaded|secured|tested|inspected|briefed|authorised|authorized)\b",
    r"\b(?:isolation|lockout|lock out|permit|guard|harness|barricade|gas test) "
    r"(?:was |were )?(?:not (?:applied|done|used|in place|obtained)|missing|absent)\b",
    r"\b(?:bypassed|defeated|overrode|overridden|disabled) the \w+(?:\s+\w+)?\b",
    # Roman-Hindi barrier constructions survive preprocessing when the lexicon cannot map the
    # whole clause. The one barrier span in the 20-row sample is exactly this shape:
    # "bina lock off nahi karna chahiye".
    r"\bbina \w+(?:\s+\w+){0,3}",
))


def _compile_modified(nouns: tuple[str, ...], modifiers: tuple[str, ...]) -> tuple[re.Pattern, ...]:
    """One pattern per noun: the noun, optionally preceded by one known modifier.

    Longest nouns first so "gas cylinder" wins over "cylinder" and "drill pipe" over "pipe".
    """
    modifier_group = "|".join(re.escape(word) for word in modifiers)
    return tuple(
        re.compile(rf"\b(?:(?:{modifier_group})\s+)?{re.escape(noun)}\b", re.IGNORECASE)
        for noun in sorted(nouns, key=len, reverse=True)
    )


LOCATION_PATTERNS = (
    tuple(
        re.compile(rf"\b(?:at |in |on )?{name}(?:\s+(?:{'|'.join(SITE_TYPES)}))?\b", re.IGNORECASE)
        for name in SITE_NAMES
    )
    + _compile_modified(PLACE_NOUNS, PLACE_MODIFIERS)
)
EQUIPMENT_PATTERNS = _compile_modified(EQUIPMENT_NOUNS, EQUIPMENT_MODIFIERS)

# Ordered by how much a wrong span costs the highlighting. barrier_failure is the most specific
# and the most load-bearing claim, so it wins a tie; activity is the widest and yields.
TYPE_PRIORITY = ("barrier_failure", "equipment", "location", "activity")

PATTERNS_BY_TYPE = {
    "barrier_failure": BARRIER_PATTERNS,
    "equipment": EQUIPMENT_PATTERNS,
    "location": LOCATION_PATTERNS,
    "activity": ACTIVITY_PATTERNS,
}


def _span(text: str, start: int, end: int) -> tuple[str, int, int] | None:
    """Trim trailing filler off a match and slice the text back out at the final offsets.

    Every returned span goes through here, which is what makes `text[start:end] ==
    entity_text` structurally true: the text is a slice of `text` at the very offsets being
    returned, so there is no second copy that could disagree.
    """
    while end > start and not text[end - 1].isalnum():
        end -= 1
    while start < end and not text[start].isalnum():
        start += 1
    if end <= start:
        return None
    return text[start:end], start, end


def _resolve_overlaps(candidates: list[tuple[str, str, int, int]]) -> list[tuple[str, str, int, int]]:
    """Keep the longest span at each position; drop anything that crosses an accepted one.

    Overlapping spans would nest or interleave the highlighter's markup. Ties break by
    TYPE_PRIORITY so the choice is deterministic rather than dependent on dict ordering.
    """
    candidates.sort(key=lambda c: (c[2], -(c[3] - c[2]), TYPE_PRIORITY.index(c[0])))
    accepted: list[tuple[str, str, int, int]] = []
    for candidate in candidates:
        if all(candidate[2] >= kept[3] or candidate[3] <= kept[2] for kept in accepted):
            accepted.append(candidate)
    return accepted


def extract_precursors(text: str) -> list[tuple[str, str, int, int]]:
    """Return [(entity_type, entity_text, span_start, span_end)], non-overlapping, in text order.

    FROZEN SIGNATURE. `text[span_start:span_end] == entity_text` for every tuple returned.
    An empty list is valid, and three of the four entity types is the normal case.
    """
    # INTERIM_LANE_A - pattern matcher. Replace this body with the spaCy entity ruler.
    if not text:
        return []

    candidates = []
    for entity_type in TYPE_PRIORITY:
        for pattern in PATTERNS_BY_TYPE[entity_type]:
            for match in pattern.finditer(text):
                trimmed = _span(text, match.start(), match.end())
                if trimmed:
                    entity_text, start, end = trimmed
                    candidates.append((entity_type, entity_text, start, end))

    return _resolve_overlaps(candidates)
