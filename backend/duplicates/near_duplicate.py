"""Detect whether a newly submitted report is a near-duplicate of one already on file.

WHY THIS EXISTS. The Site/Activity Density Ranking (`PRD.md` § Frontend pages, "the single
most important screen") is a SIF rate per site. If the same real incident gets filed twice -
two people reporting the same near-miss, or one person resubmitting after a network hiccup -
it silently inflates that site's count and its rate. This is a credibility problem in the
headline number, not a cosmetic one (Lane D brief, task 4).

THIS MODULE ONLY DETECTS. Wiring it into the ingest path (`routes/reports.py`, owned by Lane
C) or into the density query (`routes/analytics.py`, owned by Lane B) is a cross-lane change
this lane does not make itself - see the DIY.md entry logged alongside this file.

METHOD, AND ITS HONEST LIMITS. Character-level similarity via `difflib.SequenceMatcher`,
stdlib only, no new dependency. A ratio at or above `SIMILARITY_THRESHOLD` against an
existing report is called a near-duplicate. This is a blunt instrument: it will not catch two
reports describing the same incident in very different words, and it will flag two genuinely
different short reports that happen to share most of their words (two unrelated "worker fell"
reports) as duplicates. A more precise method (entity overlap, embeddings) is future work, not
implemented here - stated rather than hidden.
"""

from difflib import SequenceMatcher

SIMILARITY_THRESHOLD = 0.85


def find_near_duplicate(candidate_text: str, existing_texts: list[str]) -> str | None:
    """Return the first existing text `candidate_text` is a near-duplicate of, or None.

    Compares `cleaned_text` values, not `raw_text` - preprocessing already normalizes
    spelling and acronyms, so two reports of the same incident are more likely to match
    after cleaning than before it. Empty or whitespace-only text is never a duplicate of
    anything: two blank strings are not the same incident, they are two absences of one.
    """
    if not candidate_text or not candidate_text.strip():
        return None
    for existing in existing_texts:
        if not existing or not existing.strip():
            continue
        ratio = SequenceMatcher(None, candidate_text, existing).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            return existing
    return None