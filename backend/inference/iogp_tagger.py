"""IOGP Life-Saving Rule tagging. One public function, `tag_iogp_rules`.

THE SIGNATURE IS FROZEN (`STAGES.md` § FROZEN files):
`tag_iogp_rules(text) -> list[(rule_name, confidence)]`. Only the body changes in Block 8.

MULTI-LABEL, NOT MULTI-CLASS. `PRD.md` § ML pipeline detail specifies a 9-way **sigmoid** head:
zero, one, or several rules per report, each with an independent confidence. So the scores
below deliberately do NOT sum to 1, and returning an empty list is a correct answer - an
ordinary same-level trip maps to no rule at all. Anything that normalizes these numbers across
rules has turned the sigmoid head back into a softmax one and broken the contract.

Rule names are emitted verbatim from `schemas.IOGP_RULE_NAMES`, the canonical 9 in `PRD.md`
§ Glossary, which says do not rename or merge them. Nothing here can invent a tenth rule: the
scores are keyed by those constants, so a typo is an import error rather than a bad row.
"""

from schemas import IOGP_RULE_NAMES

MODEL_VERSION = "interim-keyword-0.1"

# A rule is emitted at or above this score. Independent per rule, as a sigmoid head is.
TAG_THRESHOLD = 0.5

# INTERIM_LANE_A - everything below is interim scaffolding. Delete the bodies, keep the
# signature. Owner: Lane A, Day 2 (DECISIONS.md, "Interim inference implementations behind
# frozen signatures").
#
# PROVENANCE. The cue phrases per rule are the prose form of the rule definitions in
# `scripts/localize_dataset.py` (the STAGE 2 prompt) - the same definitions the dataset's
# `iogp_rules` labels were generated against. Using a different notion of "Line of Fire" here
# than the labels were made with would put the interim tagger and the training data in
# disagreement, which is the failure this shared provenance exists to prevent.
#
# STRONG vs WEAK. A strong cue names the governed mechanism directly ("welding" is Hot Work).
# A weak cue is consistent with the rule but not sufficient alone ("cylinder" suggests lifting
# only if something is being moved). Two weak cues clear the threshold; one does not.
STRONG_WEIGHT = 0.55
WEAK_WEIGHT = 0.3
SCORE_CEILING = 0.9

# Ordered as `IOGP_RULE_NAMES`. Each entry: (strong cues, weak cues).
RULE_CUES = {
    "Bypassing Safety Controls": (
        ("bypass", "overrode", "overridden", "override the", "guard was removed",
         "guard removed", "without the guard", "guard missing", "interlock", "defeated",
         "disabled the alarm", "alarm was off", "tied down the trip", "jumper"),
        ("guard", "alarm", "trip", "sensor", "safety device", "protective device"),
    ),
    "Confined Space": (
        ("confined space", "cellar pit", "inside the tank", "inside the vessel",
         "entered the tank", "entered the vessel", "manhole", "sump", "into the pit",
         "gas test", "atmosphere test", "oxygen deficien"),
        ("tank", "vessel", "pit", "sump", "cellar", "ventilation", "fumes", "oxygen"),
    ),
    "Driving": (
        ("driving", "drove", "was driving", "collision", "collided", "overturned", "rollover",
         "jack knifed", "jackknifed", "ran off the road", "reversing", "reversed into",
         "from the moving", "fell from the vehicle", "run over by the"),
        ("vehicle", "truck", "tractor", "atv", "jeep", "bus", "trailer", "road", "driver"),
    ),
    "Energy Isolation": (
        ("lockout", "lock out", "tagout", "tag out", "lockout tagout", "not isolated",
         "without isolating", "isolation was not", "started while", "started up while",
         "energised", "energized", "live wire", "electric shock", "electrocut",
         "residual pressure", "stored pressure", "still under pressure", "short circuit"),
        ("maintenance", "cleaning", "repair", "servicing", "adjustment", "isolation",
         "breaker", "switchgear", "electrical", "pressure"),
    ),
    "Hot Work": (
        ("welding", "welded", "cutting torch", "gas cutting", "grinding", "grinder",
         "flame", "spark", "sparks", "hot work", "ignition source", "blowtorch", "brazing"),
        ("ignited", "fire", "burn", "burns", "smoke", "flammable", "torch"),
    ),
    "Line of Fire": (
        # "fell on" / "fell onto" are deliberately absent, and the reason is worth keeping: a
        # bare "fell on" matches "slipped and fell on his back", which is a same-level slip and
        # the labeling rule's canonical negative. Line of Fire needs something falling ONTO a
        # person, so only the person-directed forms are matched. The same phrase caused the same
        # false positive in `sif_classifier.py`; both lists carry the fix.
        ("struck by", "hit by", "fell on him", "fell on her", "fell on them",
         "fell on the worker", "fell onto him", "fell onto her", "fell onto them",
         "line of fire", "falling object",
         "dropped object", "swinging", "shifting load", "load shifted", "pinch point",
         "pinned", "pinched between", "crushed between", "trapped under", "caught in",
         "entangled", "rolled onto", "spray", "jet", "discharged", "released onto"),
        ("path of", "underneath", "beneath the", "in front of", "nearby", "rotating",
         "moving", "falling"),
    ),
    "Safe Mechanical Lifting": (
        ("crane", "hoist", "hoisting", "sling", "slung", "rigging", "lifting the",
         "was lifted", "being lifted", "suspended load", "winch", "chain block",
         "forklift", "shackle", "stacked", "stacking"),
        ("load", "lift", "trolley", "cart", "unload", "unloading", "loaded", "cylinder",
         "drum", "pipe rack", "stack"),
    ),
    "Work Authorisation": (
        ("permit to work", "without a permit", "without permit", "no permit", "permit was not",
         "without authorisation", "without authorization", "not authorised", "not authorized",
         "without a job safety analysis", "no job safety analysis", "procedure was not",
         "without following the procedure", "toolbox talk was not"),
        ("permit", "authorisation", "authorization", "procedure", "job safety analysis",
         "clearance", "supervisor was not informed"),
    ),
    "Working at Height": (
        ("fall from height", "fell from height", "fall to lower level", "fell from the",
         "fell off the", "at height", "working at height", "scaffold", "monkeyboard",
         "monkey board", "derrick", "harness", "lanyard", "fall arrest", "edge protection",
         "from the platform", "from the ladder", "from the stair", "from the mast"),
        ("ladder", "stair", "stairs", "platform", "elevated", "above ground", "roof",
         "climbing", "descending"),
    ),
}

# The dataset's own negative case: an ordinary slip or trip on a walking surface maps to NO
# rule (the STAGE 2 prompt says so explicitly, and 8 of the 20 sample rows have an empty list).
# Without this, "fell" plus "platform" would tag Working at Height on a same-level trip.
SAME_LEVEL_ONLY = (
    "same level", "slipped on", "slipped and fell", "tripped over", "tripped on",
    "lost his footing", "lost her footing", "lost their footing", "stumbled", "uneven surface",
)
HEIGHT_OVERRIDES_SAME_LEVEL = (
    "fall to lower level", "fell from the", "fell off the", "from the scaffold",
    "from the ladder", "from the stair", "from the platform", "at height", "into the pit",
    "into the cellar",
)


def _score(lowered: str, strong: tuple[str, ...], weak: tuple[str, ...]) -> float:
    """Independent score for one rule. Not normalized against the other eight."""
    hits = sum(STRONG_WEIGHT for cue in strong if cue in lowered)
    hits += sum(WEAK_WEIGHT for cue in weak if cue in lowered)
    return min(SCORE_CEILING, hits)


def tag_iogp_rules(text: str) -> list[tuple[str, float]]:
    """Return [(rule_name, confidence)] for every applicable rule. Empty list is valid.

    FROZEN SIGNATURE. Confidences are independent per rule and do not sum to 1.
    """
    # INTERIM_LANE_A - keyword scorer. Replace this body with the sigmoid multi-label head.
    lowered = text.lower()

    same_level = (any(cue in lowered for cue in SAME_LEVEL_ONLY)
                  and not any(cue in lowered for cue in HEIGHT_OVERRIDES_SAME_LEVEL))

    tagged = []
    for rule_name in IOGP_RULE_NAMES:
        if same_level and rule_name == "Working at Height":
            continue
        strong, weak = RULE_CUES[rule_name]
        score = _score(lowered, strong, weak)
        if score >= TAG_THRESHOLD:
            tagged.append((rule_name, round(score, 3)))

    # Highest confidence first: the Detail view renders these as chips left to right, and the
    # most probable rule is the one an HSE officer should read first.
    tagged.sort(key=lambda pair: -pair[1])
    return tagged
