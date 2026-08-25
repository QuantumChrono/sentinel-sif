# SOURCE.md — provenance of the raw OSHA dataset

## File

| | |
|---|---|
| Path | `data/raw/January2015toNovember2025.csv` |
| Size | 57,403,269 bytes |
| SHA-256 | `406ffe7bc0758a447ad1650171b9c3f6990f901e8b73f167dad7cf60a97f13cd` |
| Data rows | **105,996** (106,488 physical lines — narratives contain embedded newlines, so `wc -l` overcounts) |
| Columns | 28 |
| Event date range | 2015-01-01 → 2025-11-30 (all 105,996 dates parse as `%m/%d/%Y`, zero failures) |
| On-disk mtime | 2026-08-24 20:29 IST |
| Downloaded by | Swayam, manually (Day 0 `DIY.md` item) |

## Dataset

**OSHA Severe Injury Reports (SIR)** — U.S. Department of Labor, Occupational Safety and
Health Administration. Employer-submitted reports of work-related severe injuries under
**29 CFR 1904.39**, covering federal-OSHA and state-plan jurisdictions.

Landing page: `https://www.osha.gov/severeinjury` (verified reachable, HTTP 200, 2026-08-24)

### Direct CSV URL — NOT VERIFIED

**The exact download URL for this file is unconfirmed.** The landing page renders its
download table client-side; no `.csv` link exists anywhere in the served HTML (checked the
full 102 KB response — zero occurrences of the string `csv`). Four candidate URL patterns
under `osha.gov/sites/default/files/` were probed and all returned **HTTP 404**.

Rather than record a plausible-looking URL that was never confirmed to serve this exact
file, this line is left open. Logged in `DIY.md`: the human who performed the download
supplies the URL from their browser history, and it gets pasted here verbatim.

The **file itself** is fully pinned by the SHA-256 above, so provenance of the bytes is
reproducible even while the URL line is open.

## Reporting scope — the defining property of this dataset

OSHA operates **two separate reporting channels**, and this dataset is only one of them
(confirmed from the landing-page text):

| Outcome | Channel | In this file? |
|---|---|---|
| Inpatient hospitalization | 24-hour report | yes |
| Amputation | 24-hour report | yes |
| Loss of an eye | 24-hour report | yes |
| **Employee killed on the job** | **8-hour report — separate stream** | **no** |

**There is therefore no fatality column, and effectively no fatal cases.** This is a
structural property of the source, not a gap in the download. See `data/LABELING_RULE.md`
§ "The fatality problem" for what this forces on the labeling rule.

## License and attribution

Works of the U.S. federal government are not subject to domestic copyright protection
(**17 U.S.C. § 105**), which is the basis on which this dataset is treated as public domain
and freely redistributable.

Note honestly: **the landing page carries no explicit license, copyright, or attribution
statement.** The grep for `license` / `public domain` / `attribution` / `copyright` in the
page body returned nothing but generic DOL site-footer links. So the attribution line below
is our own good practice, not a term OSHA imposes.

Attribution used in the app and any submission:

> Source data: OSHA Severe Injury Reports (Jan 2015 – Nov 2025), U.S. Department of Labor,
> Occupational Safety and Health Administration. Public domain. Narratives in SentinelSIF
> are LLM-rewritten into an Indian oil-and-gas context; no OSHA record appears verbatim.

Employer names, street addresses, and coordinates are present in the raw file and are
**dropped, never localized**, when synthetic records are generated — the synthetic set must
not carry a real U.S. company's name attached to a rewritten narrative.

## Integrity

`data/raw/` is git-ignored except `*.md` (root `.gitignore`), so the 57 MB CSV is never
committed. This file is the committed record of it. The raw CSV is **read-only** for the
rest of the project — nothing writes to `data/raw/`.

Re-verify at any time:

```bash
sha256sum data/raw/January2015toNovember2025.csv
# expect 406ffe7bc0758a447ad1650171b9c3f6990f901e8b73f167dad7cf60a97f13cd
```
