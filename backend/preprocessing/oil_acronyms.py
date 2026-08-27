"""Hand-built OIL/oilfield acronym dictionary. Data only, no logic.

Expanded BEFORE spellcheck, so the spellchecker never sees a bare acronym and never
"corrects" one into an English word.

PROVENANCE MATTERS HERE. `STAGES.md` Block 4 forbids guessing at an OIL acronym without
marking it unverified, so every entry below is one of:
  - standard drilling/HSE industry usage, or
  - standard Indian upstream (OIL/ONGC) usage,
and anything I was not confident about is listed in UNVERIFIED and deliberately NOT
applied. An acronym expanded wrongly is worse than one left alone: the expansion becomes
the text the classifier and the NER read, so a wrong guess silently rewrites the incident.

Keys are matched case-insensitively on whole words only. Values are inserted lower case:
DistilBERT tokenizes an uncased model anyway, and rebuilding the original casing pattern is
machinery that buys nothing downstream.

Also holds DOMAIN_WORDS - the oilfield and Indian-upstream vocabulary the spellchecker must
NOT touch. It lives here because it is the same kind of thing: hand-curated domain
vocabulary, kept as data next to the acronyms rather than buried in the pipeline.
"""

# Standard HSE and permit vocabulary. Universal across operators.
SAFETY = {
    "ppe": "personal protective equipment",
    "loto": "lockout tagout",
    "ptw": "permit to work",
    "jsa": "job safety analysis",
    "hse": "health safety and environment",
    "hira": "hazard identification and risk assessment",
    "hazop": "hazard and operability study",
    "msds": "material safety data sheet",
    "sds": "safety data sheet",
    "scba": "self contained breathing apparatus",
    "lel": "lower explosive limit",
    "h2s": "hydrogen sulphide",
    "co2": "carbon dioxide",
    "ert": "emergency response team",
    # Added Day 2. The project's own vocabulary and the standard HSE terms around it. `sif`
    # matters most: a report that says "potential SIF" should read as the words the classifier
    # was fine-tuned on, not as an opaque token DistilBERT splits into wordpieces.
    "sif": "serious injury or fatality",
    "lti": "lost time injury",
    "trir": "total recordable incident rate",
    "moc": "management of change",
    "tbt": "toolbox talk",
    "jha": "job hazard analysis",
    "hazid": "hazard identification",
    "simops": "simultaneous operations",
    "iogp": "international association of oil and gas producers",
    "lsr": "life saving rule",
    "flra": "field level risk assessment",
    "tra": "task risk assessment",
    "cse": "confined space entry",
    "wah": "work at height",
    "frc": "fire retardant clothing",
    "mpi": "magnetic particle inspection",
    "dpt": "dye penetrant test",
}

# Standard drilling and well-operations vocabulary.
DRILLING = {
    "bop": "blowout preventer",
    "bha": "bottom hole assembly",
    "rih": "run in hole",
    "pooh": "pull out of hole",
    "wob": "weight on bit",
    "rop": "rate of penetration",
    "td": "total depth",
    "npt": "non productive time",
    "dp": "drill pipe",
    "csg": "casing",
    "tbg": "tubing",
    "wl": "wireline",
    "ct": "coiled tubing",
    # "wo" deliberately NOT mapped to workover: it is Hindi for "that" and collides.
    "srp": "sucker rod pump",
    "esp": "electrical submersible pump",
    "pcp": "progressive cavity pump",
    "dg": "diesel generator",
    "dg set": "diesel generator set",
    # Added Day 2. Pressure vocabulary first: these are the terms a barrier-failure narrative
    # actually turns on, so leaving them as bare tokens loses the part that carries the hazard.
    "psv": "pressure safety valve",
    "prv": "pressure relief valve",
    "esdv": "emergency shutdown valve",
    "mawp": "maximum allowable working pressure",
    "whp": "wellhead pressure",
    "thp": "tubing head pressure",
    "chp": "casing head pressure",
    "sithp": "shut in tubing head pressure",
    "sicp": "shut in casing pressure",
    "ibop": "internal blowout preventer",
    "mgs": "mud gas separator",
    "octg": "oil country tubular goods",
    "lcm": "lost circulation material",
    "ecd": "equivalent circulating density",
    "dls": "dogleg severity",
    "tvd": "true vertical depth",
    "wbm": "water based mud",
    "obm": "oil based mud",
    "rkb": "rotary kelly bushing",
    "hpht": "high pressure high temperature",
}

# Indian upstream (OIL / ONGC) surface-facility vocabulary.
INDIAN_UPSTREAM = {
    "ggs": "group gathering station",
    "ocs": "oil collecting station",
    "eps": "early production system",
    "cts": "central tank station",
    "ctf": "central tank farm",
    # Added Day 2. Operators and the two statutory bodies whose names appear in Indian
    # upstream incident paperwork.
    "ongc": "oil and natural gas corporation",
    "oisd": "oil industry safety directorate",
    "dgms": "directorate general of mines safety",
    "lpg": "liquefied petroleum gas",
    "cng": "compressed natural gas",
    "lng": "liquefied natural gas",
}

# Plain field-note shorthand. Not acronyms, but the same substitution and the same reason.
FIELD_SHORTHAND = {
    "eqpt": "equipment",
    "eqp": "equipment",
    "mtr": "metre",
    "mtrs": "metres",
    "approx": "approximately",
    "hrs": "hours",
    "wrk": "work",
    "maint": "maintenance",
    "opr": "operator",
    "sup": "supervisor",
    "inj": "injury",
    "hosp": "hospital",
    "amb": "ambulance",
    "veh": "vehicle",
}

# Real words that an English dictionary does not hold, so pyspellchecker would "correct"
# them into something else. Every one appears in the generated corpus or the PRD glossary.
# Protecting them is not cosmetic: "drawworks" -> "driveworks" or "khalasi" -> "kalashi"
# rewrites the equipment and the job title the NER is meant to extract.
DOMAIN_WORDS = {
    # equipment and rig structure
    "drawworks", "workover", "monkeyboard", "kelly", "derrick", "tong", "tongs",
    "casing", "tubing", "wellhead", "christmas", "annulus", "swab", "swabbing",
    "sucker", "elevator", "elevators", "slips", "cellar", "flowline", "manifold",
    "separator", "knockout", "flare", "pigging", "rathole", "mousehole", "kickoff",
    "topdrive", "mudline", "shaker", "shakers", "desander", "desilter", "choke",
    "genset", "bullnose", "crossover", "nipple", "spool", "gasket", "bund",
    # roles, Indian and industry
    "khalasi", "khalasis", "toolpusher", "roustabout", "roughneck", "banksman",
    "rigger", "riggers", "fitter", "fitters", "jawan", "havildar",
    "sirdar", "contractual",  # mistri/majdoor/mazdoor live in HINGLISH: they normalize to English
    # sites and regions from schema.sql, plus nearby geography
    "duliajan", "naharkatiya", "moran", "baghjan", "makum", "hapjan", "tanot",
    "ramgarh", "assam", "rajasthan", "dibrugarh", "tinsukia", "jaisalmer",
    "assamese", "brahmaputra",
    # common Indian given names, so a name is never spell-corrected into a word
    "ramesh", "suresh", "rajesh", "mahesh", "amit", "sunil", "anil", "vijay",
    "raju", "ravi", "mohan", "arun", "deepak", "sanjeev", "vinod", "ashok",
    "rakesh", "dinesh", "manoj", "pradeep", "sanjay", "ajay", "bikash", "dipak",
    "jitendra", "narayan", "gopal", "bharat", "kishore", "prakash", "hemant",
    # `jwala` is here for a measured reason, not for completeness: adding "wala" to the Hinglish
    # lexicon made it a known word, which gave the name `jwala` a one-edit neighbour it did not
    # have before, and the corpus census caught it being rewritten to "wala" twice. Protecting a
    # name is cheap; a fix that quietly renames a worker is not.
    "jwala",
}

ACRONYMS = {**SAFETY, **DRILLING, **INDIAN_UPSTREAM, **FIELD_SHORTHAND}

# NOT APPLIED. Every one of these appears in real field text but has more than one
# plausible reading, or I could not confirm the OIL-specific meaning. Expanding a coin
# flip corrupts the incident, so they pass through untouched and stay recorded here.
# Resolve them with a real OIL glossary or an operations SME, then move them up.
UNVERIFIED = {
    "dsv": "drilling supervisor? diving support vessel? - appears as a job title in the "
           "generated dataset; the offshore reading is certainly wrong onshore",
    "wd": "working day? well data? - seen in generated heavy-noise text",
    "temp": "temperature? temporary? - both are common in maintenance notes",
    "oim": "offshore installation manager - offshore role, no onshore equivalent",
    "mop": "manner of production? maximum operating pressure?",
    "tt": "toolbox talk? tool test?",
    "sh": "shift? safety hazard?",
    "lt": "low tension (electrical)? light?",
    "ht": "high tension (electrical)? height?",
    "cp": "cathodic protection? control panel?",
    "pm": "preventive maintenance? afternoon?",
    # Added Day 2 alongside the expansion above. Each was considered for the applied lists and
    # deliberately refused - the first four because a common English word or unit shares the
    # spelling, which is the collision that corrupts ordinary reports, and the rest because two
    # readings are equally live in this exact context.
    "sop": "standard operating procedure - but 'sop' is an ordinary English word, so mapping it "
           "would rewrite plain text",
    "peso": "Petroleum and Explosives Safety Organisation (India) - collides with the currency, "
            "which an English dictionary holds",
    "mw": "mud weight? megawatt? - both are live on a site with a diesel generator",
    "tds": "top drive system? total dissolved solids? - both appear in oilfield text",
    "ut": "ultrasonic testing - but 'ut' collides with English and is only two characters",
    "rt": "radiographic testing? running tool? - two characters, too many readings",
    "gl": "ground level? gas lift? - both ordinary onshore",
    "pob": "personnel on board - standard offshore; the onshore reading is a camp head count "
           "and this project is onshore, so the same objection applies as to 'oim'",
    "nmr": "near miss report? nuclear magnetic resonance? - the logging tool reading is real",
    "swp": "safe work permit? safe working practice? - overlaps 'ptw', which IS mapped",
}

# Longest first, so "dg set" is matched before "dg" and never becomes "diesel generator set"
# via two passes. Sorted here, once, rather than at every call.
ACRONYMS_BY_LENGTH = sorted(ACRONYMS.items(), key=lambda kv: -len(kv[0]))
