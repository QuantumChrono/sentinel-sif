"""`GET /api/v1/sites` - the list the Intake page's site selector is built from.

WHY THIS ENDPOINT EXISTS AND IS NOT IN `PRD.md` § Backend API. That table lists the seven endpoints
that carry reports and analytics; it does not name a way to read `sites`, and the Intake page
cannot offer a real site selector without one. The two alternatives were both worse: reading
`sites` from the browser's Supabase client is a second data path with no server validation in
front of it and does not currently work at all (the anon role has no grants - `42501 permission
denied`, `AUDIT.md` 2026-08-25), and hard-coding the eight seeded sites in the frontend would
mock a table that already exists.

It returns the frozen `SiteOut` from `schemas.py` - the same shape already embedded in every
report response - so no contract was added, only a way to read one that was already there.

Ordered by name so the selector does not reshuffle between page loads, and returns `[]` rather
than raising on an empty database.
"""

from fastapi import APIRouter

from database import supabase
from schemas import SiteOut

router = APIRouter(prefix="/api/v1/sites", tags=["sites"])


@router.get("", response_model=list[SiteOut])
def list_sites() -> list[SiteOut]:
    """Every site, alphabetically. Read-only: sites are seeded by `schema.sql`, never by the UI."""
    rows = supabase.table("sites").select(
        "id, name, region, latitude, longitude").order("name").execute().data or []
    return [SiteOut(**row) for row in rows]
