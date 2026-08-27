"""Turn a raw field report into cleaned text, in PRD order: acronyms, spellcheck, Hinglish.

One public function, `clean_report(raw_text)`. It NEVER raises: every stage is wrapped, and
any failure degrades to the text that went into that stage. A preprocessing crash would
take down the whole synchronous inference request, so returning slightly-worse text always
beats returning an exception.

WHY THE ORDER MATTERS, AND THE TRAP IN IT
`PRD.md` fixes the order as acronym expansion -> spellcheck -> Hinglish normalization. Run
naively that order destroys the Hindi: pyspellchecker does not know `nahi`, `bina` or
`chahiye`, so it "corrects" them into English lookalikes before stage 3 ever sees them, and
the Hinglish stage then finds nothing to normalize. The order is kept as specified and the
spellchecker is given a protected vocabulary instead - acronym expansions, oilfield domain
words, and every Roman-Hindi key in the lexicon. Reordering the stages would have been the
other fix; protecting the vocabulary keeps the documented contract and is narrower.

Acronyms expand first for the same reason: an unexpanded `ppe` or `bop` is not an English
word either, and a spellchecker left alone with it produces "pope" or "top".

CONFIDENCE AND GRACEFUL DEGRADATION
`language_detected` is one of `en`, `hi-en`, `hi`. Confidence is the share of non-English
words the Hinglish lexicon could actually account for. Below CONFIDENCE_FLOOR the normalized
text is thrown away and the ORIGINAL text is returned with the flag set, because a
half-normalized sentence is worse for a classifier than an untouched one. Devanagari script
cannot be normalized by a Roman-script lexicon at all, so it returns the original outright.
"""

import re
from collections import Counter

from spellchecker import SpellChecker

from .hinglish_lexicon import HINGLISH, HINGLISH_BY_LENGTH
from .oil_acronyms import ACRONYMS_BY_LENGTH, DOMAIN_WORDS

# Below this share of accountable non-English words, the normalization is not trusted and the
# original text is returned instead. 0.5 is a starting point chosen against the 10 Block 4
# samples, not a tuned value - it needs a real sweep once labelled data exists.
CONFIDENCE_FLOOR = 0.5

# Words shorter than this are never spell-corrected. Short tokens have many near-neighbours,
# so a 3-letter typo correction is close to a coin flip and can invent a different word.
MIN_SPELLCHECK_LENGTH = 4

# A word with more than this many edit-distance-1 neighbours is left alone. The correction is a
# popularity contest between near-ties at that point, and pyspellchecker settles it on corpus
# frequency, which knows nothing about oilfields or Hindi. Measured on the real 326-row corpus:
# `chai` has 14 candidates and became "chair", `waqt` has 8 and became "want". Every genuine
# typo worth fixing has few: equipmnt 1, leakge 1, hosptal 1, pressre 3, valv 4.
MAX_SPELLCHECK_CANDIDATES = 4

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

# Apostrophes are part of the word, NOT a boundary. `[a-zA-Z]+` split "didn't" into `didn` + `t`,
# and `didn` is 4 characters so it cleared the length gate and got "corrected" to `did` - so the
# pipeline turned "the operator didn't lock out the valve" into "did't lock out", deleting the
# negation. `hinglish_lexicon.py` calls negation the highest-value group in the corpus precisely
# because it is what turns a narrative into a barrier-failure signal, and this quietly destroyed
# it in plain English reports. The dictionary already knows "didn't", "wasn't" and "worker's", so
# keeping the token whole is the entire fix.
WORD = re.compile(r"[a-zA-Z]+(?:'[a-zA-Z]+)*")

# One shared instance: loading the frequency list costs ~100ms and the inference path is
# synchronous. Never mutated after construction, so it is safe to share across requests.
_SPELL = SpellChecker(distance=1)  # distance=1: edit-distance-2 guesses are too speculative

# Everything the spellchecker must leave alone. Acronym expansions are included because
# stage 1 has already inserted them by the time stage 2 runs.
PROTECTED = (
    DOMAIN_WORDS
    | set(HINGLISH)
    | {word for _, expansion in ACRONYMS_BY_LENGTH for word in expansion.split()}
    | {key for key, _ in ACRONYMS_BY_LENGTH}
)
_SPELL.word_frequency.load_words(PROTECTED)


def expand_acronyms(text):
    """Stage 1. Replace known acronyms with their expansions, longest key first.

    Whole-word matching only: a substring match would rewrite `dp` inside `dpressure`, and
    the same class of bug already cost this project a wrong metric once.
    """
    for acronym, expansion in ACRONYMS_BY_LENGTH:
        text = re.sub(rf"\b{re.escape(acronym)}\b", expansion, text, flags=re.IGNORECASE)
    return text


def _is_letter_substitution(word, correction):
    """True when the correction swaps letters rather than adding, dropping or moving them.

    THE MEASURED SEPARATOR between a typo worth fixing and a foreign word worth sparing. A
    typist who means "equipment" drops or transposes letters - `equipmnt`, `wtaer`, `hosptal`,
    `clearnig` - so the correction restores a letter or reorders one. A Hindi word that merely
    lands near an English one needs a letter *exchanged* to get there: `gaye`->`gave`,
    `mein`->`mean`, `liye`->`like`, `dono`->`done`, `baad`->`bad`, `thik`->`this`.

    Same length with a different multiset of letters is exactly that exchange. Measured over the
    real 326-row corpus: this gate spares 21 of 34 sampled Hinglish words and costs 2 of 34
    genuine typos (`maintenence`, `laddar`, which now pass through unchanged). That trade is
    deliberate - an unfixed typo still tokenizes into subwords close to the right word, while a
    confident wrong substitution hands the classifier a different word entirely.
    """
    return len(word) == len(correction) and Counter(word) != Counter(correction)


def correct_spelling(text):
    """Stage 2. Fix obvious typos, leaving protected vocabulary and short words alone.

    Four gates, cheapest first. Anything that trips one is returned untouched, because the
    failure mode being defended against is not a missed typo - it is a confidently rewritten
    word, which silently changes what the classifier and the NER downstream read.
    """
    def fix(match):
        word = match.group(0)
        lowered = word.lower()
        # A possessive is protected by its stem. Making apostrophes part of the token (above)
        # turned `khalasi's` into one word that the dictionary does not hold, even though
        # `khalasi` is in DOMAIN_WORDS - so the most-rewritten word in the whole corpus became
        # `khalasi's` -> `khalasis`, 5 occurrences. Checking the stem covers every protected
        # noun's possessive without listing them twice.
        stem = lowered[:-2] if lowered.endswith("'s") else lowered
        if len(stem) < MIN_SPELLCHECK_LENGTH or stem in _SPELL:
            return word
        # Ambiguity gate: too many near-neighbours means the "correction" is a frequency
        # coin flip. Checked before `correction()` because both walk the same candidate set.
        if len(_SPELL.candidates(lowered) or ()) > MAX_SPELLCHECK_CANDIDATES:
            return word
        correction = _SPELL.correction(lowered)
        if not correction or correction == lowered:
            return word
        if _is_letter_substitution(lowered, correction):
            return word
        # Preserve the shape the writer used; the models downstream are uncased but the
        # cleaned text is also shown to a human in the Report Detail view.
        return correction.capitalize() if word[0].isupper() else correction

    return WORD.sub(fix, text)


def normalize_hinglish(text):
    """Stage 3. Map Roman-script Hindi to English. Returns (text, mapped, unaccounted).

    `mapped` counts words the lexicon replaced. `unaccounted` counts words that are neither
    English, nor protected domain vocabulary, nor in the lexicon - i.e. probably Hindi we
    cannot handle. The two together are what the confidence is computed from.
    """
    mapped = 0
    for hindi, english in HINGLISH_BY_LENGTH:
        text, count = re.subn(rf"\b{re.escape(hindi)}\b", english, text, flags=re.IGNORECASE)
        mapped += count

    unaccounted = sum(
        1 for word in WORD.findall(text)
        if word.lower() not in _SPELL and word.lower() not in PROTECTED
    )
    return text, mapped, unaccounted


def clean_report(raw_text):
    """Run the three stages and report what happened. Never raises.

    Returns a dict: `cleaned_text`, `language_detected`, `normalization_confidence`,
    `degraded` (True when the original text was returned instead of the normalized one),
    and `notes` (why, in one human-readable line).
    """
    if raw_text is None or not str(raw_text).strip():
        return _result("", "en", 1.0, False, "empty input")

    text = str(raw_text)

    # Devanagari cannot be normalized by a Roman-script lexicon. Returning the original is
    # the honest answer; guessing at transliteration here would be inventing content.
    if DEVANAGARI.search(text):
        return _result(text, "hi", 0.0, True,
                       "Devanagari script present; Roman-script lexicon cannot normalize it")

    try:
        expanded = expand_acronyms(text)
    except Exception as error:  # a bad pattern must not take down the request
        return _result(text, "en", 0.0, True, f"acronym stage failed: {type(error).__name__}")

    try:
        spelled = correct_spelling(expanded)
    except Exception:
        spelled = expanded  # keep going: stage 3 is still worth attempting

    try:
        normalized, mapped, unaccounted = normalize_hinglish(spelled)
    except Exception as error:
        return _result(spelled, "en", 0.0, True,
                       f"hinglish stage failed: {type(error).__name__}; acronyms kept")

    language = "hi-en" if mapped else "en"
    # No non-English words at all means nothing to be unsure about, so confidence is 1.0
    # rather than 0/0. This is the ordinary clean-English path, 60% of the corpus.
    denominator = mapped + unaccounted
    confidence = 1.0 if denominator == 0 else mapped / denominator

    if language == "en" and unaccounted == 0:
        return _result(normalized, "en", 1.0, False, "clean English; no normalization needed")

    if confidence < CONFIDENCE_FLOOR:
        return _result(
            text, language, round(confidence, 3), True,
            f"normalization confidence {confidence:.2f} below {CONFIDENCE_FLOOR}; "
            f"{unaccounted} unrecognized word(s) against {mapped} mapped - original returned")

    return _result(normalized, language, round(confidence, 3), False,
                   f"{mapped} Hindi word(s) normalized, {unaccounted} unrecognized")


def _result(cleaned_text, language_detected, confidence, degraded, notes):
    return {
        "cleaned_text": cleaned_text,
        "language_detected": language_detected,
        "normalization_confidence": confidence,
        "degraded": degraded,
        "notes": notes,
    }
