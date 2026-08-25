"""Roman-script Hindi to English word map. Data only, no logic.

Every key here was taken from Hindi that actually appears in the generated field reports
(`data/sample/localized.jsonl`), not from a general Hindi word list. Normalizing words the
corpus never uses buys nothing and risks collisions.

THE COLLISION RULE IS THE WHOLE DESIGN CONSTRAINT. Several very common Hindi words are
spelled exactly like common English words: Hindi `the` (were), `do` (two), `par` (on/but),
`se` (from), `is` (this), `to` (then), `main` (I), `din` (day), `ho` (be). Mapping any of
them would corrupt ordinary English reports, which are 60% of the corpus. They are listed
in COLLIDES_WITH_ENGLISH, deliberately NOT mapped, and a self-check asserts none of them
leaks into HINGLISH. Losing a few Hindi words is the cheap failure; rewriting English text
is the expensive one.
"""

# Negation and absence. The highest-value group: these are what turn a narrative clause
# into a barrier-failure signal, so losing them costs more than losing any other group.
NEGATION = {
    "nahi": "not", "nahin": "not", "naa": "no",
    "bina": "without", "kabhi": "ever", "koi": "any", "kuch": "some",
}

# Verbs and verb tails, in the forms the corpus actually uses.
VERBS = {
    "karna": "to do", "karo": "do", "kiya": "did", "karke": "having done",
    "hua": "happened", "hui": "happened",
    "gaya": "went", "gayi": "went", "gir": "fell", "girna": "to fall",
    "girgaya": "fell", "aaya": "came", "aayi": "came", "laga": "started",
    "lagaya": "applied", "lagayi": "applied", "chalna": "to walk",
    "chal": "walk", "chalu": "running", "khula": "open",
    "kaha": "said", "bola": "said", "bataya": "told", "maana": "obeyed",
    "dekha": "saw", "socha": "thought", "utha": "lifted", "uthaya": "lifted",
    "rakha": "placed", "khol": "open", "khola": "opened", "todna": "to break",
    "tut": "broke", "tuta": "broke", "phat": "burst", "nikla": "came out",
    "bach": "escaped", "bacha": "escaped", "mila": "found", "diya": "gave",
    "chahiye": "should", "chahiye tha": "should have",
}

# Nouns: body parts, people, equipment-adjacent and site words.
NOUNS = {
    "haath": "hand", "paer": "leg", "ungli": "finger",
    "aankh": "eye", "kamar": "back", "khoon": "blood",
    "dard": "pain", "chot": "injury", "chott": "injury",
    "aadmi": "man", "admi": "man", "aurat": "woman", "bhai": "brother",
    "saab": "sir", "sahab": "sir", "mistri": "fitter", "majdoor": "labourer", "mazdoor": "labourer",
    "kaam": "work", "kaam karna": "to work",
    "paani": "water", "tel": "oil", "aag": "fire", "garmi": "heat",
    "hawa": "air", "dhuan": "smoke", "keechad": "mud",
    "seedhi": "ladder", "seedhiyan": "stairs", "chabi": "key",
    "rassi": "rope", "taar": "wire", "gaadi": "vehicle",
    "jagah": "place", "andar": "inside", "bahar": "outside", "upar": "above",
    "neeche": "below", "saamne": "in front", "peeche": "behind",
}

# Adverbs, adjectives and connectives. Sentence glue; safe to map only where the
# spelling does not collide with English.
MODIFIERS = {
    "bahut": "very", "zyada": "excessive", "jyada": "excessive",
    "thoda": "slightly", "bilkul": "completely", "pura": "complete",
    "poora": "complete", "jaldi": "quickly", "dheere": "slowly",
    "achha": "good", "accha": "good", "kharab": "bad", "galat": "wrong",
    "sahi": "correct", "theek": "fine", "tez": "fast", "tej": "fast",
    "bhaari": "heavy", "halka": "light", "purana": "old", "naya": "new",
    "dhyan": "attention", "dhyaan": "attention", "khatra": "danger",
    "lekin": "but", "kyunki": "because", "isliye": "therefore",
    "phir": "then", "abhi": "now", "sab": "all",
    "wahan": "there", "yahan": "here", "kaise": "how", "kyun": "why",
    "seedha": "straight", "aese": "like this", "aise": "like this",
}

# Auxiliaries that do NOT collide with English. `the` and `ho` are excluded on purpose.
AUXILIARY = {
    "hai": "is", "hain": "are", "tha": "was", "thi": "was", "thay": "were",
    "raha": "continuing", "rahi": "continuing", "rahe": "continuing",
    "usne": "they", "usko": "them", "uska": "their", "uski": "their",
    "unhone": "they", "humne": "we", "tumne": "you",
    "yeh": "this", "woh": "that",
}

# Taken from the Block 4 10-sample run: every word below was observed being corrupted by the
# spellchecker because the lexicon could not account for it. Same provenance rule as the rest
# of this file - these are words the corpus actually uses, not a general Hindi word list.
FROM_SAMPLES = {
    "saaf": "clean", "turant": "immediately", "hisa": "part", "hissa": "part",
    "tezz": "fast", "yaha": "here", "itna": "so much", "itni": "so much",
    "chillaya": "shouted", "chilaya": "shouted", "meri": "my", "mera": "my",
    "bhi": "also", "unka": "their", "unki": "their",
    "dhakka": "jolt", "chalana": "to drive", "chalaya": "drove", "rakhe": "keep",
    "rakhna": "to keep", "aisa": "like this", "agar": "if", "hota": "happens",
    "hoti": "happens", "uske": "their", "usse": "them", "kam": "less",
    "pada": "fell", "padi": "fell", "gyi": "went", "bhat": "distracted",
    "gir pada": "fell down", "gir gaya": "fell down", "ho gaya": "happened",
    "ho gayi": "happened", "slip ho gaya": "slipped",
    "turat": "immediately", "sliped": "slipped",
}

HINGLISH = {**FROM_SAMPLES, **NEGATION, **VERBS, **NOUNS, **MODIFIERS, **AUXILIARY}

# NEVER MAP THESE. Each is a real Hindi word whose spelling is also a common English word,
# so mapping it would rewrite English reports. The self-check asserts the intersection with
# HINGLISH is empty; add to this set before adding any lookalike to a group above.
COLLIDES_WITH_ENGLISH = {
    "the", "do", "par", "se", "is", "to", "so", "ho", "le", "na", "hi", "us",
    "main", "mere", "more", "din", "are", "an", "in", "on", "at", "no", "be",
    "he", "it", "was", "were", "can", "man", "men", "may", "kar", "ki", "ka",
    "ko", "ke", "sab ko", "bad", "sat", "pat", "tan", "ban", "dam", "jam",
    "lag", "log", "log in", "aur", "ek", "sir", "pair", "mat", "wo", "jo", "band",
    "hone", "niche", "jab",
}

# The 11 remaining HINGLISH keys that an English dictionary also holds. Every one was
# reviewed against THIS corpus and accepted: each is either a proper noun (Saab the car,
# Bach, Purana), a rare register (phat, tut, karo syrup, agar the lab gel), or a word no
# oilfield incident report uses in its English sense. They are mapped deliberately.
#
# This set exists so the self-check can assert that NO OTHER lexicon key collides with
# English. That gate is the real fix: `sir`, `pair`, `log`, `mat` and `hone` all shipped as
# silent collisions because the only assertion was that HINGLISH and COLLIDES_WITH_ENGLISH
# are disjoint, which passes happily while a collision sits in HINGLISH alone. Adding a key
# that English knows now fails the check until it is reviewed and listed here.
REVIEWED_ENGLISH_LOOKALIKES = {
    "agar", "bach", "bola", "gaya", "hui", "karo", "phat", "purana", "saab", "sab", "tut",
}

# Longest first so multiword keys ("kaam karna") match before their parts.
HINGLISH_BY_LENGTH = sorted(HINGLISH.items(), key=lambda kv: -len(kv[0]))
