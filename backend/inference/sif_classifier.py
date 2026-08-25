"""SIF-potential classification. One public function, `classify_sif`.

THE SIGNATURE IS FROZEN (`STAGES.md` § FROZEN files): `classify_sif(text) -> (bool, float)`.
Only the body below changes when the fine-tuned DistilBERT weights land.

WHAT THE FLOAT MEANS, NOW AND AFTER THE SWAP. It is the confidence in the *returned verdict* -
the predicted class's probability, which is exactly what a softmax head gives you. So a
confident negative is `(False, 0.88)`, not `(False, 0.12)`. `routes/reports.py` compares it
against `CONFIDENCE_THRESHOLD` without caring which class won, and that comparison keeps
working unchanged after Block 8 precisely because the interim mirrors the final semantics.
"""

import re

# Written into `classifications.model_version` on every row, so a query can always separate
# interim-scored rows from real-model rows after the swap. Lane A bumps this with the weights.
MODEL_VERSION = "interim-keyword-0.1"

# Short reports cannot support a confident verdict from keywords alone. `PRD.md` § Edge cases
# requires a very short valid report to land in the review queue rather than receive a forced
# confident answer, so the score is pulled back toward 0.5 below this many words.
MIN_WORDS_FOR_CONFIDENCE = 8

# INTERIM_LANE_A - everything from here to the end of the module is interim scaffolding.
# Delete the bodies, keep the signature. Owner: Lane A, Day 2 (see DECISIONS.md, "Interim
# inference implementations behind frozen signatures").
#
# PROVENANCE OF THESE KEYWORDS, because a made-up word list is not defensible on stage. Every
# group below is the prose form of a mechanism class in `data/LABELING_RULE.md` § 5 - the same
# rule that labels the training data - so the interim classifier and the real labels agree on
# what counts as high-energy. Group names cite the test they come from.
#
# THE HONEST LIMITATION: the labeling rule matches OSHA's *coded title* fields, which are a
# closed vocabulary. This matches free prose, which is not. So these keywords approximate the
# rule; they do not implement it. That gap is the reason this whole file is interim.

# Test A1 - falls to a lower level. Not a same-level slip.
FALL_FROM_HEIGHT = (
    "fall from height", "fell from height", "fall to lower level", "fell to the lower",
    "fell from the", "fell off the", "fall through", "fell through", "from the scaffold",
    "from the derrick", "from the monkeyboard", "from the platform", "from the ladder",
    "from the stair", "from the roof", "from the mast", "at height", "working at height",
)

# A1 again, reached the other way. A narrative often states the fall and the height separately -
# "fell approximately eleven feet while erecting a pipe scaffold" contains no phrase above, yet
# is the clearest possible fall-to-lower-level. A fall verb plus a structure that only exists at
# height is the same mechanism expressed across two clauses, so both halves are required.
FALL_VERBS = ("fell", "fall", "falling", "slipped off", "lost his footing", "lost her footing",
              "lost their footing", "missed a step", "missed his step", "stepped off")
HEIGHT_STRUCTURES = ("scaffold", "derrick", "monkeyboard", "monkey board", "mast", "platform",
                     "ladder", "stair", "stairs", "stairway", "staircase", "gantry", "roof",
                     "catwalk", "walkway above", "upper deck", "landing", "trench", "excavation",
                     "cellar pit", "into the pit")

# Test A2 - struck by, dropped, swinging, shifting, rolling. The largest positive class.
#
# TWO PHRASES WERE DELIBERATELY REMOVED FROM THIS GROUP after they fired on the 20-row sample,
# and both are recorded because the omissions would otherwise look like oversights:
#   - "fell on" matched "slipped and fell on his back" - a same-level slip, the rule's canonical
#     negative. Only the object-onto-person direction is a strike, so the person forms below are
#     matched explicitly instead.
#   - "spray" matched "spray herbicide on the well pad" - routine agricultural spraying. The
#     mechanism is a pressurized release, so the pressure qualifier is now required.
STRUCK_BY_OBJECT = (
    "struck by", "hit by", "falling object", "dropped object", "fell on him", "fell on her",
    "fell on them", "fell on the worker", "fell onto him", "fell onto her", "fell onto them",
    "swinging", "shifting load", "load shifted", "slipped from the sling", "rolled onto",
    "roll onto", "rolled over", "run over", "pinned", "pinched between", "crushed between",
    "jammed his", "jammed her", "jammed their", "was crushed", "trapped under", "line of fire",
    "pressurized spray", "pressurised spray", "high pressure spray", "pressure spray",
    "pressure washer", "jet", "discharged",
)

# A bare "caught between" is deliberately NOT in the group above, and this is the sharpest
# judgment call in the file. Three sample rows read almost identically in prose - a finger or
# hand caught between two things - but the labeling rule splits them on the coded event: a hand
# between shifting 200 kg pipe racks is A2 positive, while a fingertip in a belt grinder's
# rollers is negative, because § 5 Test B excludes amputation as a mechanism. Prose does not
# carry that distinction, so "caught between" would flip the grinder row positive. The
# shifting-mass forms are matched instead, and the residual gap is the approximation this whole
# interim file is honest about.

# Test A2 - stored, rotating or live energy released. Includes the barrier reasoning the rule
# states explicitly: equipment turning under someone's hands during maintenance is positive.
UNCONTROLLED_ENERGY = (
    "caught in", "entangled", "rotating", "started while", "started up while", "energised",
    "energized", "live wire", "electric shock", "electrocut", "short circuit", "flashover",
    "pressure released", "under pressure", "stored pressure", "blowout", "kick", "burst",
    "ruptured", "explosion", "exploded", "fire", "ignited", "ignition", "flash",
)

# Test A2 - vehicle momentum.
VEHICLE = (
    "collision", "collided", "overturned", "rollover", "rolled the vehicle", "jack knifed",
    "jackknifed", "ran off the road", "off the driving surface", "reversed into",
    "hit the pedestrian", "struck the pedestrian",
)

# Test A2 - atmosphere and engulfment.
ATMOSPHERE_ENGULFMENT = (
    "confined space", "cellar pit", "inside the tank", "inside the vessel", "oxygen",
    "asphyxi", "h2s", "hydrogen sulphide", "hydrogen sulfide", "toxic gas", "fumes",
    "inhaled", "engulf", "cave in", "caved in", "collapsed", "buried", "drown", "submerged",
)

# Test B - an injury only lethal-grade energy transfer can produce. NOTE the deliberate
# absence of "amputation": § 5 Test B excludes it, because a limb lost to a low-energy machine
# is permanent but not a fatality mechanism. Amputations reach positive through the event
# instead. Keeping that asymmetry here is what makes this an energy test, not a severity test.
LETHAL_GRADE_INJURY = (
    "intracranial", "skull fracture", "internal injur", "internal bleeding", "internal organ",
    "haemorrhage", "hemorrhage", "spinal cord", "paralys", "quadripleg", "parapleg",
    "crush injur", "crushing", "third degree", "fourth degree", "unconscious", "cardiac",
    "heat stroke", "multiple fractures",
)

# Explicitly NOT high-energy. § 5 A1 carves sub-6-foot falls out, and a same-level slip is the
# rule's canonical negative ("a same-level slip cannot kill you at a different angle"). These
# pull the score down so the ordinary trip report is a confident negative, not a coin flip.
SAME_LEVEL = (
    "same level", "slipped on", "slipped and fell", "tripped over", "tripped on",
    "lost his footing", "lost her footing", "lost their footing", "uneven surface",
    "wet floor", "walking when", "stumbled",
)

POSITIVE_GROUPS = (
    FALL_FROM_HEIGHT, STRUCK_BY_OBJECT, UNCONTROLLED_ENERGY, VEHICLE, ATMOSPHERE_ENGULFMENT,
)

# Score arithmetic. Deliberately coarse: these are three round numbers, not tuned parameters,
# and presenting a keyword count as a calibrated probability would be the dishonest version.
# Real calibration arrives with the weights and the validation sweep in Block 8.
NO_EVIDENCE_SCORE = 0.5      # no signal either way - lands under the threshold, goes to review
PER_MECHANISM_WEIGHT = 0.18  # each distinct high-energy mechanism class present
LETHAL_INJURY_WEIGHT = 0.22  # Test B evidence: the injury itself proves the energy
SAME_LEVEL_WEIGHT = 0.20     # per same-level phrase, pulling toward negative
SCORE_CEILING = 0.92         # a keyword match never justifies near-certainty
SCORE_FLOOR = 0.08

WORD = re.compile(r"[A-Za-z0-9]+")
NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")

# § 5 A1 carves sub-6-foot falls out of the positive class, so a stated height has to be read
# rather than ignored. Feet only: 6 ft is the rule's own boundary, and any height stated in
# metres large enough to appear in a report is already above it. Spelled numbers are included
# because the sample states one as "fell approximately eleven feet".
STATED_FEET = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|foot)\b")
SPELLED_FEET = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty)\s+"
    r"(?:ft|feet|foot)\b")
SPELLED_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                   "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
                   "twenty": 20}
SUB_SIX_FEET = 6.0

# A2's `caught in running` in prose form. Both halves are required: a bare "caught on" is often
# a snagged sleeve, while a catch against equipment that is turning is the mechanism the rule
# names. Kept as a pair for the same reason as FALL_VERBS - one word alone decides nothing.
CATCH_VERBS = ("caught in", "caught on", "caught between", "got caught", "entangled", "dragged into")
MOVING_EQUIPMENT = ("winch", "belt", "pulley", "sprocket", "shaft", "rotating", "revolving",
                    "spinning", "wheel", "roller", "rollers", "conveyor", "gear", "gears",
                    "coupling", "flywheel", "auger", "augur", "drum", "running")


def _normalize(text: str) -> str:
    """Lowercase, punctuation to spaces, collapse runs. `LABELING_RULE.md` § 5 step 0, verbatim.

    This is not cosmetic and it is not optional. The labeling rule mandates the same pass for
    the same reason: `jack-knifed` and `jackknifed` are the same mechanism, and a substring list
    that matches only one of them silently labels the other negative. § 9.10 of that document
    records 1,775 rows lost to exactly this class of bug - the failure is silent, which is why
    it is fixed by normalizing once here rather than by enumerating spelling variants forever.

    Safe here precisely because this module returns no offsets. `precursor_ner.py` must NEVER do
    this: its spans have to index the exact string the caller passed in.
    """
    return NON_ALPHANUMERIC.sub(" ", text.lower()).strip()


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(needle in haystack for needle in needles)


def _states_only_a_short_fall(lowered: str) -> bool:
    """True when the text states a height and every height stated is under 6 feet.

    `LABELING_RULE.md` § 5 A1 excludes `less than 6 feet` from the positive class, so a report
    that volunteers "tumbled about 4 ft" is telling us the fall was below the rule's boundary.

    The MAXIMUM stated height decides, not the first or the smallest: a narrative mentioning
    both a 4-foot step and an 11-foot fall describes an 11-foot fall. No height stated returns
    False - absence of a number is not evidence of a short drop.
    """
    heights = [float(value) for value in STATED_FEET.findall(lowered)]
    heights += [float(SPELLED_NUMBERS[word]) for word in SPELLED_FEET.findall(lowered)]
    return bool(heights) and max(heights) < SUB_SIX_FEET


def classify_sif(text: str) -> tuple[bool, float]:
    """Return (sif_potential, confidence_in_that_verdict).

    FROZEN SIGNATURE. Confidence is the predicted class's probability, so it is high for a
    confident negative too - see the module docstring.
    """
    # INTERIM_LANE_A - keyword scorer. Replace this body with the DistilBERT forward pass.
    lowered = text.lower()
    normalized = _normalize(text)
    words = WORD.findall(normalized)

    # Heights are read off `lowered`, not `normalized`: step-0 turns a decimal point into a
    # space, so "4.5 ft" would otherwise be read as "5 ft".
    sub_six_foot_fall = _states_only_a_short_fall(lowered)

    present = [_contains_any(normalized, group) for group in POSITIVE_GROUPS]
    # The two-part mechanisms: neither half decides anything alone (see FALL_VERBS and
    # CATCH_VERBS). A fall below 6 feet is carved out of A1 by the labeling rule, so a stated
    # short height disqualifies the fall mechanism rather than merely weakening it.
    fall_from_height = (_contains_any(normalized, FALL_VERBS)
                        and _contains_any(normalized, HEIGHT_STRUCTURES))
    if sub_six_foot_fall:
        present[0] = False
        fall_from_height = False
    caught_in_running = (_contains_any(normalized, CATCH_VERBS)
                         and _contains_any(normalized, MOVING_EQUIPMENT))

    mechanisms = sum(present) + fall_from_height + caught_in_running
    score = NO_EVIDENCE_SCORE + mechanisms * PER_MECHANISM_WEIGHT
    if _contains_any(normalized, LETHAL_GRADE_INJURY):
        score += LETHAL_INJURY_WEIGHT

    # Same-level phrasing only argues down when no high-energy mechanism was found. A worker
    # who slipped *and* fell into the cellar pit is a fall to a lower level, and letting the
    # word "slipped" cancel that would invert the label on a genuine SIF case.
    if mechanisms == 0:
        score -= sum(SAME_LEVEL_WEIGHT for phrase in SAME_LEVEL if phrase in normalized)

    score = max(SCORE_FLOOR, min(SCORE_CEILING, score))

    # Too little text to justify either verdict: pull halfway back to 0.5, which puts the
    # result under CONFIDENCE_THRESHOLD and routes it to a human instead of guessing.
    if len(words) < MIN_WORDS_FOR_CONFIDENCE:
        score = NO_EVIDENCE_SCORE + (score - NO_EVIDENCE_SCORE) / 2

    sif_potential = score > NO_EVIDENCE_SCORE
    confidence = score if sif_potential else 1.0 - score
    return sif_potential, round(confidence, 3)
