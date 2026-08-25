"""Self-check for the preprocessing pipeline. Run directly, no framework needed:

    backend/.venv/Scripts/python.exe -m backend.preprocessing.test_clean_report

Asserts the promises the other three files make in prose, so a broken promise fails loudly
instead of silently rewriting field reports. The data invariants come first: they are the
ones that corrupt every downstream stage when they break.
"""

from .clean_report import clean_report, expand_acronyms, normalize_hinglish
from spellchecker import SpellChecker

from .hinglish_lexicon import (COLLIDES_WITH_ENGLISH, HINGLISH,
                               REVIEWED_ENGLISH_LOOKALIKES)
from .oil_acronyms import ACRONYMS, DOMAIN_WORDS, UNVERIFIED

CHECKS = []


def check(name, got, want):
    CHECKS.append((name, got, want))


# --- data invariants -------------------------------------------------------------------
# The lexicon docstring promises no English lookalike is ever mapped. Asserted, not trusted:
# mapping "the" or "do" would rewrite the 60% of the corpus that is plain English.
check("no english lookalike mapped", sorted(COLLIDES_WITH_ENGLISH & set(HINGLISH)), [])
# An acronym cannot be both applied and unverified; that would apply a guess we disowned.
check("no acronym both applied and unverified", sorted(set(ACRONYMS) & set(UNVERIFIED)), [])
check("no acronym maps to itself",
      [k for k, v in ACRONYMS.items() if k == v], [])
check("no hinglish word maps to itself",
      [k for k, v in HINGLISH.items() if k == v], [])
# THE GATE THAT WAS MISSING. Asserting HINGLISH and COLLIDES_WITH_ENGLISH are disjoint does
# NOT catch a collision that exists only in HINGLISH - which is how "sir", "pair", "log",
# "mat" and "hone" shipped. Ask the English dictionary directly instead: any key it knows
# must have been reviewed and listed, or this fails.
# A FRESH dictionary, deliberately not the pipeline's `_SPELL`: that one has PROTECTED
# loaded into it, and PROTECTED contains every HINGLISH key, so it "knows" all of them by
# construction and the gate would flag the entire lexicon.
_PLAIN_ENGLISH = SpellChecker(distance=1)
check("no unreviewed english collision",
      sorted(k for k in HINGLISH
             if " " not in k and k in _PLAIN_ENGLISH
             and k not in REVIEWED_ENGLISH_LOOKALIKES), [])
# Gender: Hindi third-person pronouns are gender-neutral, so mapping one to "he" or "her"
# invents a gender the report never stated. they/them is the accurate reading.
check("pronouns not gendered",
      sorted(k for k, v in HINGLISH.items() if v in {"he", "she", "him", "her", "his", "hers"}),
      [])
# A domain word that is also a Hinglish key would be normalized away instead of protected.
check("domain words and hinglish disjoint", sorted(DOMAIN_WORDS & set(HINGLISH)), [])

# --- acronym expansion -----------------------------------------------------------------
check("acronym expands", expand_acronyms("worker had no PPE"),
      "worker had no personal protective equipment")
check("acronym case insensitive", expand_acronyms("bop tested"), "blowout preventer tested")
# The substring bug that already cost this project a wrong metric once, asserted here.
check("acronym needs word boundary", expand_acronyms("dpressure rising"), "dpressure rising")
check("longest acronym key wins", expand_acronyms("the DG set tripped"),
      "the diesel generator set tripped")
check("unverified acronym untouched", expand_acronyms("the DSV signed"), "the DSV signed")

# --- hinglish normalization ------------------------------------------------------------
check("hindi negation mapped", normalize_hinglish("bina lock off nahi kiya")[0],
      "without lock off not did")
check("english lookalike survives", normalize_hinglish("the men were on the rig")[0],
      "the men were on the rig")

# --- clean_report contract -------------------------------------------------------------
# Never raises, on anything. Each of these would be a 500 during a live demo.
for label, bad in [("none", None), ("empty", ""), ("blank", "   "), ("int", 12345),
                   ("emoji", "\U0001f525\U0001f525"), ("symbols", "!!! ??? ###"),
                   ("long", "a" * 5000), ("newlines", "\n\n\t\t")]:
    try:
        result = clean_report(bad)
        ok = isinstance(result, dict) and "cleaned_text" in result
    except Exception as error:
        ok = f"RAISED {type(error).__name__}"
    check(f"no crash on {label}", ok, True)

clean = clean_report("The fitter was replacing a gasket on the wellhead at Duliajan.")
check("clean english undegraded", clean["degraded"], False)
check("clean english language", clean["language_detected"], "en")
check("clean english confidence", clean["normalization_confidence"], 1.0)
check("clean english text unchanged", clean["cleaned_text"],
      "The fitter was replacing a gasket on the wellhead at Duliajan.")

mixed = clean_report("Worker ko chot lagi, usne bina PPE kaam kiya tha")
check("mixed script flagged", mixed["language_detected"], "hi-en")
check("mixed script expands acronym",
      "personal protective equipment" in mixed["cleaned_text"], True)
check("mixed script normalizes hindi", "without" in mixed["cleaned_text"], True)

devanagari = clean_report("मजदूर को चोट लगी")
check("devanagari returns original", devanagari["cleaned_text"], "मजदूर को चोट लगी")
check("devanagari language", devanagari["language_detected"], "hi")
check("devanagari degraded", devanagari["degraded"], True)

# Unrecognized Hindi the lexicon cannot account for must degrade to the original text
# rather than emit a half-rewritten sentence.
garbled = clean_report("qwrtz plkjh zxcvb mnbvc lkjhg poiuy")
check("unrecognized text degrades", garbled["degraded"], True)
check("unrecognized keeps original", garbled["cleaned_text"],
      "qwrtz plkjh zxcvb mnbvc lkjhg poiuy")

# Protected vocabulary must survive the spellchecker. These are the words whose corruption
# would rewrite the equipment or the job title the NER is meant to extract.
for word in ("drawworks", "khalasi", "toolpusher", "Duliajan", "monkeyboard"):
    check(f"spellcheck spares {word}", word in clean_report(f"the {word} was there")["cleaned_text"], True)

# A real typo still gets fixed, or the stage is doing nothing.
check("real typo corrected", "equipment" in clean_report("the equipmnt failed")["cleaned_text"], True)

# Every result carries the full contract, so a caller can rely on the keys existing.
for key in ("cleaned_text", "language_detected", "normalization_confidence", "degraded", "notes"):
    check(f"result has {key}", key in clean_report("test report text"), True)


def main():
    failed = 0
    for name, got, want in CHECKS:
        ok = got == want
        failed += not ok
        shown = ascii(got)  # cp1252 console: never print raw non-ASCII
        print(f"  {'ok  ' if ok else 'FAIL'} {name:36} got {shown[:44]:<46} want {ascii(want)}")
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
