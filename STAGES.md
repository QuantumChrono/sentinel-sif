# STAGES.md — Execution plan, current position, and lane ownership

This file is the single source of truth for **where the project is** and **what the current session is allowed to touch**. Read the "Current Position" block first, every session, before anything else.

Status marks: `[ ]` not started · `[~]` in progress · `[x]` done and verified. Never mark `[x]` from memory — only after actually running the exit check.

---

## Current Position

```
DAY:        Day 2 CLOSED - all four lanes merged and integrator-verified 2026-08-27.
MODE:       Transitioning to the single remaining milestone: FINAL CONSOLIDATION (see below).
            Days 3, 4 and 5 are collapsed into it. Lane ownership and the FROZEN list below
            still apply.
INTEGRATOR: Swayam (sole owner of merges and FROZEN files)

VERIFIED ON MERGED `main` 2026-08-27 (every number run, none carried over):
            pytest 21 passed / 1 xfailed / 0 failed  ·  inference self-check 22/22
            npx tsc --noEmit 0 errors  ·  npx eslint . 0 problems  ·  npm run build succeeds
            density.py self-check passed  ·  span invariant 81/81 spans, 0 mismatches
            `ruff` STILL absent from the venv and both requirements files, so the backend has
            no linter and none ran. `CLAUDE.md` documents `ruff check .`; it does not run.

DEPLOYED:   CHANGED 2026-08-27 - Render is RETIRED as the backend host (`DECISIONS.md`).
            frontend -> Vercel, Root Directory `frontend` (unchanged).
            backend  -> localhost FastAPI exposed by a secure tunnel (`cloudflared` /
                        `localtunnel`). Forced by two measured blockers, neither configurable
                        away: 885 MB site-packages + 537 MB weights vs Render free tier's
                        512 MB ceiling, and `model_weights/` is `.gitignore`d so the weights
                        cannot reach Render by push at all.
            database -> Supabase managed Postgres (unchanged).
            NOT YET MEASURED: nothing has been tunnelled or timed. The "~60 ms" figure behind
            this choice is a target, not an observation - it is deliberately in `DECISIONS.md`
            and NOT in `AUDIT.md`. Only measured latency is local: ~384 ms pipeline, 5.6 ms
            inference. Tunnel URL changes on restart unless NAMED, and
            `NEXT_PUBLIC_API_BASE_URL` is baked at Vercel build time -> redeploy (`DIY.md`).
            The root `Dockerfile` is on NO deploy path; deletion still flagged in `DIY.md`.

BASELINE:   Block 8 is DONE - real weights are live, not blocked. `grep` finds 0 `INTERIM_LANE_A`,
            0 `INTERIM`, 0 `TODO`, 0 `FIXME` in any `.py`/`.ts`/`.tsx` under `backend/`
            or `frontend/`. Live weights (513 MB in `backend/model_weights/`) are byte-identical
            to Lane A's retrained staging copy - sha256 verified, so the swap `DIY.md` asks for
            is already done and repo-root `model_weights/` is a redundant 257 MB.
            SIF CLASSIFIER, held-out test n=49: accuracy 0.5918, F1 0.5833, separation +0.1126,
            T 1.2011, 12 of 49 below the 0.65 threshold. Weak but no longer degenerate - it
            predicts both classes and the auto-publish path exists. Validation n=42: 0.6905.
            DATABASE, counted 2026-08-27: reports 50, classifications 50, iogp_tags 46,
            precursors 139, sites 8, users 3. `model_version` 40 `distilbert-sif-1.0` +
            10 `interim-keyword-0.1` (the 10 ad-hoc rows `DIY.md` asks a decision on - one
            holds the project's only human `overridden` decision). Reports: 39 `needs_review`,
            11 `processed`. Reviews: 46 auto, 2 confirmed, 2 overridden.
            DATASET: `data/processed/localized.jsonl` 326 rows, `train.jsonl` 277,
            `data/test/test.jsonl` 49, `data/sample/localized.jsonl` 20. Block 3's 1,200-row
            target was never reached and is not being pursued (Groq token ceiling, `DIY.md`).
            DEMO SEED now 50 processed reports, which MEETS Block 9's "~50" line that was
            partial at 20 - composition stated above rather than presented as a clean 50.
            `PATTERNS.md` is still the reference implementation every lane copies.

KNOWN OPEN: NO PAGE HAS BEEN RENDERED IN A BROWSER BY AN AGENT. Unchanged and still the biggest
            gap: no Playwright in the repo and the pages are client-rendered, so the empty-database
            case is proven at the API layer and injection structurally - neither on a screen.
            The signed-in pass over both roles is the human's, on the live URLs (`DIY.md`).
            `PATTERNS.md` and `README.md` still carry stale INTERIM_LANE_A prose (`DIY.md`).
            PII redaction and near-duplicate detection are tested but wired into NO production
            path - 9 of 22 tests exercise code that cannot run in production (`AUDIT.md`).
            Tagger covers 8 of 9 IOGP rules; `Work Authorisation` has 0 training rows and is
            untrainable, so the system must NOT be described as covering all 9.

PORTS:      Local only. Port 8000 is occupied by an UNRELATED service; this backend runs on 8001.
            USE `http://127.0.0.1:8001`, NOT `localhost:8001`, for any local timing: the
            IPv4-only bind makes `localhost` pay a failed IPv6 attempt per connection
            (`GET /health` 2649 ms vs 615 ms).
```

Update this block on every day change, lane change, and block completion. It is the first thing any agent reads after a context clear.

---

## The operational model

| Day | Who | Purpose |
|---|---|---|
| **Day 0** | Me | Accounts, keys, repo, local toolchain. No app code. |
| **Day 1** | Me + agent, Mode A | Build the **entire working baseline end to end**. Every page real, every endpoint real, real data flowing. This day establishes the architectural pattern the whole team copies. |
| **Day 2** | Team, Mode B | Lanes deepen Tier 1 quality on top of the baseline. I verify and force-correct after they push. |
| **Day 3** | Team, Mode B | Tier 2 features + integration polish. I verify and force-correct after they push. |
| **Day 4** | Team, Mode B | Hardening, deploy, edge cases, demo rehearsal. Feature freeze at end of day. |
| **Day 5** | — | **Buffer. Nothing scheduled.** Reserved for slippage, and nothing else. |

The Day 1 baseline is not a prototype to be replaced. It is the reference implementation. Days 2–4 extend it; they do not re-architect it.

---

# Day 1 — Baseline build (Mode A, sequential)

Work blocks top to bottom. Do not start a later block's deliverable early. Two blocks run as background wall-clock jobs (dataset generation, model training) — the timeline deliberately overlaps them with hands-on work; that overlap is the reason one day is enough.

## Block 1 — Scaffold
- [ ] `frontend/` (Next.js App Router + TS + Tailwind), `backend/` (FastAPI), `.env.example` in both, root `.gitignore`
- [ ] Governance files (`PRD.md`, `STAGES.md`, `AGENTS.md`, `CLAUDE.md`, `DECISIONS.md`, `AUDIT.md`, `DIY.md`) committed at repo root
- Do NOT: install ML libraries, write business logic, touch Supabase
- Exit: `npm run dev` serves a page; `uvicorn main:app` returns `{"status":"ok"}` on `/health`

## Block 2 — Database schema
- [ ] Supabase tables exactly matching `PRD.md` § Database schema — `sites`, `reports`, `classifications`, `iogp_tags`, `precursors`, `users`. Any deviation needs a `DECISIONS.md` entry.
- [ ] 6–8 real-sounding `sites` rows seeded (Assam/Rajasthan OIL-style names, real lat/long)
- [ ] Manual insert + select verified against every table
- Do NOT: add columns "we'll probably need," add indexes before a measured slow query, enable RLS yet
- Exit: every table accepts an insert and returns it; schema file committed as `backend/schema.sql`

## Block 3 — Dataset (background job starts here)
- [ ] OSHA SIR narratives downloaded unmodified to `data/raw/`, exact URL + date recorded in `data/raw/SOURCE.md`
- [ ] `data/LABELING_RULE.md` written **before** any label is generated — the `sif_potential` rule stated as a testable rule against OSHA severity fields. "The LLM decided" is never an acceptable rationale.
- [ ] `scripts/localize_dataset.py` — offline only, never imported by the backend. Run on 20 rows, manually review, log the review in `AUDIT.md`, then scale up.
- [ ] 2,000–3,000 records in `data/processed/`, 15% held out in `data/test/` — split before any training
- Do NOT: invent rows if the download fails (log the blocker), let the generating LLM grade its own labels unspot-checked, call this script from any runtime path
- Exit: record counts, class balance, and per-rule tag distribution logged in `AUDIT.md` with real numbers

## Block 4 — Preprocessing (hands-on, while Block 3 runs)
- [x] `backend/preprocessing/` — acronym expansion, spellcheck, Hinglish normalization, in that order
- [x] Graceful degradation: low normalization confidence returns the original text and flags `language_detected`. Never throws, never silently corrupts input.
- [x] Run against 10 hand-picked messy samples, log before/after in `AUDIT.md`
- Do NOT: import any transformer model here, make network calls, guess at OIL acronyms without noting them as unverified
- Exit: 10/10 samples processed without exception; garbage input returns something safe
- **[x] EXIT MET 2026-08-25:** 10/10 processed, no exceptions; 8 classes of garbage input all
  return a shaped dict; self-check 45/45; ruff clean. Two known limitations logged in
  `AUDIT.md` rather than fixed: output is translationese (the collision rule leaves Hindi
  function words in place on purpose), and `CONFIDENCE_FLOOR` is untuned because 0 of 10 real
  samples degraded.

## Block 5 — API contract freeze + inference interface
- [x] Pydantic request/response models for all 7 `PRD.md` endpoints in `backend/schemas.py` — **this file becomes FROZEN for Days 2–4**
- [x] Inference interface signatures fixed now, implementation swappable later:
      `classify_sif(text) -> (bool, float)` · `tag_iogp_rules(text) -> list[(rule_name, float)]` · `extract_precursors(text) -> list[(entity_type, entity_text, span_start, span_end)]`
- [x] Day-1-only interim implementations behind those exact signatures so the frontend can be built against real response shapes before weights exist
- Do NOT: build the 7 endpoints twice (no separate mock-JSON pass — the frozen Pydantic contract *is* the contract), change a signature after the frontend starts consuming it
- Exit: `POST /api/v1/reports` returns a fully-shaped real response, written to all tables, with the interim implementation
- **[x] EXIT MET 2026-08-25, with a stated caveat:** `POST /api/v1/reports` returns a fully-shaped
  `ReportDetail` (status `processed`, verdict + confidence, 5 IOGP tags, 6 precursor spans) and
  writes all four tables — verified through the HTTP layer against a **stubbed** Supabase client,
  because `backend/.env` lacks the service-role key (DIY.md, blocking). Inference self-check
  21/21; preprocessing 45/45; `ruff` clean; all 7 endpoints present in the OpenAPI spec. The span
  invariant `text[span_start:span_end] == entity_text` holds on all 38 test inputs, 0 mismatches.
  Interim bodies carry `INTERIM_LANE_A` (6 occurrences, 2 per module) for Lane A's Day 2 deletion.
- **Required `DECISIONS.md` entry:** interim implementation is scaffolding, deleted in Block 8, never a silent runtime fallback

## Block 6 — Training (background job starts here)
- [ ] Fine-tune DistilBERT SIF classifier (binary + confidence) on the Block 3 split
- [ ] Fine-tune IOGP tagger — 9-way **sigmoid** multi-label head, not softmax
- [ ] spaCy entity ruler seeded from the labeling schema
- Do NOT: touch the test split during training, tune the threshold on test data, report a metric you didn't compute
- Exit: real held-out metrics (accuracy, precision, recall, confusion matrix, per-rule F1) logged in `AUDIT.md` — no rounding up, negative results logged too

## Block 7 — Frontend (hands-on, while Block 6 runs)
- [~] Supabase Auth + role-based redirect: `hse_manager` → Dashboard, `site_supervisor` → Intake. Verify both roles actually land correctly.
      **Rule verified (`lib/role_check.ts` 16/16) and the unauthenticated path measured with curl.
      NOT verified with real accounts: none has `app_metadata.role` set (DIY.md), so every real
      session reads "no role set" and lands on /intake. Stays `[~]` until both roles are seen landing.**
- [~] Intake page — submit renders result **inline, no navigation**. This is the demo's hero interaction; it must feel instant.
      **Built, all five states explicit. Only "empty input blocked" is exercised — the backend cannot
      reach the database, so no real submit has run (AUDIT.md 2026-08-26).**
- [~] Report Detail "Magic View" — color-coded entity highlighting from real spans, verdict badge, confidence, IOGP chips
      **Built; span slicing verified 20/20 including non-BMP, overlapping and malformed offsets. Never
      rendered from a real API response. Confirm/Override will 422 until `users` is seeded (DIY.md).**
- [ ] Dashboard — KPI cards, IOGP distribution chart, and the **Site/Activity Density Ranking table**. The ranking table is the literal expected-outcome line of the problem statement; it is the priority screen, not an afterthought. Verify its ordering against a hand-computed expected order on a small known dataset.
- [ ] Review Queue — a deliberately ambiguous report must route here instead of auto-publishing
- Do NOT: build the Trends page (Tier 2, Day 3), mock any API response, hand-write a span offset
- Exit: login → submit → detail → dashboard → review works against the real API

## Block 8 — Weight swap
- [ ] Real fine-tuned weights loaded behind the Block 5 signatures; **interim implementations deleted, not routed around**
- [ ] Confidence threshold (start 0.65) tuned on the validation split, final value logged in `AUDIT.md`
- [ ] End-to-end latency measured on real hardware, logged. Target under 3s.
- Do NOT: change any frozen signature during the swap, leave a dual code path, leave a keyword fallback reachable
- Exit: same frontend, unchanged, now serving real model output; `grep` confirms no interim implementation remains

## Block 9 — Baseline close-out
- [~] ~50 pre-seeded processed reports (demo-day network-lag fallback)
- **[~] PARTIALLY MET 2026-08-26 - 20 rows, not ~50, and the shortfall is the dataset:**
  `scripts/seed_demo_reports.py` pushed all 20 rows of `data/sample/localized.jsonl` through the
  real `POST /api/v1/reports`, so they are genuinely processed rows with real classifications,
  tags and spans - not hand-written rows. It cannot reach 50 because `data/processed/` holds 0
  rows (Block 3 never started). Rows were NOT padded by duplicating narratives: that inflates
  every density denominator, and the ranking table is the screen `PRD.md` calls the literal
  expected outcome. The 5 unique rows in `data/scratch/` were also left out - `AUDIT.md` records
  that directory as not a corpus. Stays `[~]` until the dataset can supply ~50.
  SHAPE, all counted: sif true 11 / false 9; `processed` 14 / `needs_review` 6; 13 IOGP tags over
  11 rows, 9 untagged; 63 precursor spans; en 12 / hi-en 8; spread over **12 distinct days** and
  all 8 sites, giving **6 distinct rank_scores** - Moran 1/1 at 100% correctly ranks BELOW
  Naharkatiya 2/3 at 67%. Every row carries `model_version = 'interim-keyword-0.1'` and is STALE
  at the Block 8 swap - Lane A re-runs the script (`DIY.md`).
- [x] `PRD.md` edge-case table run against the real running system — one pass/fail line per case in `AUDIT.md`
- **[x] EXIT MET 2026-08-26, and it found two real bugs:** every case was RUN against the live API
  with actual input, never marked done by reasoning. Three new scripts, all re-runnable:
  `scripts/check_edge_cases.py` **16/16**, `scripts/check_prompt_injection.py` **17/17**,
  `scripts/check_empty_database.py` **6/6**. Per-case pass/fail lines with the input used and the
  observed behaviour are in `AUDIT.md` 2026-08-26.
  TWO RAW HTTP 500s FOUND AND FIXED, both forbidden by § Edge cases: (1) U+0000 in report text -
  Postgres `22P05`, uncaught because `_insert_report` catches only `23503`; fixed by a validator
  in `schemas.py`. (2) a lone surrogate - crashed FastAPI's **own** 422 handler on
  `.encode("utf-8")`, so validation worked and *reporting* it failed; fixed by an app-wide
  handler in `main.py`. Both files are FROZEN, so both need integrator sign-off (`DIY.md`).
  Both are now pinned as regression cases, and a valid surrogate pair (emoji) is asserted to
  still round-trip, proving the fix did not over-scrub.
  INJECTION - the case the brief weights most: the hazard sentence alone scores True/0.92, and
  all 5 injection payloads left the verdict at True/0.92 with tags intact. Text is stored
  character-for-character; `{{7*7}}` never became `49`; the `DROP TABLE` payload left every table
  present with exact expected counts; the service-role key is never echoed. Structurally there is
  no interpreter to reach - no LLM/outbound-HTTP client in any of 17 backend files, no
  `eval`/`exec`/`__import__`, `localize_dataset.py` imported by nothing, and no
  `dangerouslySetInnerHTML`/`innerHTML`/`eval` in any of 23 frontend files.
  NOT VERIFIED, logged open rather than smoothed over: **no page was rendered in a browser**. No
  Playwright in the repo and the pages are client-rendered, so the empty-database case is proven
  at the API layer and the injection case structurally - neither on a screen (`DIY.md`).
  Two of my own checks were wrong before the code was: an assertion flagged `RuntimeError` (the
  deliberate `type(error).__name__`) as a leaked traceback, and the dynamic-execution scanner's
  `compile\(` matched `re.compile(` and reported 4 false findings. Both corrected, and the
  scanner now carries a positive control.
- [x] **`PATTERNS.md` written** — the reference implementation index: how a route is written, how a page fetches, how errors surface, how a migration is added, naming conventions, and the file-ownership map below. Every Day 2–4 session reads this instead of re-deriving conventions.
- **[x] EXIT MET 2026-08-26 for this item only:** written from the actual code, not from
  intentions - every command in its § 0 table was run first (7/7 passing) and every abstract
  rule points at a real file. It states our own violations rather than the aspiration: the 8
  files over the ~200-line limit and their `AUDIT.md` acceptances, the missing `ruff`, and two
  docstrings whose commands do not run. § 9 gives four lanes the real numbers - 0 rows in
  `data/processed/`, 20 in `data/sample/`, no `data/test/`, 6 `INTERIM_LANE_A` markers,
  1-of-20 barrier spans, nothing deployed - each with an owner and a day. See DECISIONS.md
  2026-08-26 for why the violations are named instead of omitted.
- [x] Deploy: frontend → Vercel, backend → Render. Full flow tested on deployed URLs, not just localhost.
- **[x] MET 2026-08-26, by the integrator on the live stack:** frontend on Vercel (Root Directory
  `frontend`), backend on Render as a native Python 3 Web Service (Root Directory `backend`,
  `uvicorn main:app --host 0.0.0.0 --port $PORT`), database on Supabase. End-to-end smoke test
  passed with **zero CORS errors**, which is the specific proof that `FRONTEND_ORIGINS` matches
  the Vercel origin on scheme + host and that `NEXT_PUBLIC_API_BASE_URL` carries no trailing
  slash. Hugging Face Spaces was dropped - its Docker environments are paid - so the root
  `Dockerfile` is on no deploy path and the unbuilt-container risk is retired rather than fixed
  (`DECISIONS.md`, `AUDIT.md` 2026-08-26).
  STILL OPEN, so the exit line below is not fully closed: no agent has rendered a page in a
  browser, deployed ingest latency is not re-measured, and the signed-in pass over both roles is
  the human's on the live URLs (`DIY.md`).
- Do NOT: deploy without explicit human sign-off, skip `PATTERNS.md` because the code "reads clearly" — five parallel agents will each invent their own conventions without it
- Exit: a complete unassisted run works on deployed URLs; `PATTERNS.md` committed

---

# Days 2–4 — Mode B (parallel lanes)

## FROZEN files — read-only for every lane

Changing any of these silently breaks every other lane. It requires the integrator's explicit sign-off **and** a `DECISIONS.md` entry. No exceptions, no "one-line fix."

```
PRD.md
PATTERNS.md
backend/schemas.py          — the API contract
backend/schema.sql          — DB schema (additive migration only, integrator-approved)
backend/main.py             — app wiring and router registration
backend/inference/*.py      — the three function signatures (bodies are Lane A's)
frontend/lib/api_client.ts  — the single HTTP layer
frontend/app/layout.tsx     — shell, providers, auth wrapper
```

## Lane ownership map

Four lanes. Fewer than four teammates: one person takes two lanes, never two people one lane. More than four: split Lane D first — it has the most separable work.

**Lane A — Model quality.** Owns `backend/preprocessing/`, `backend/inference/` bodies, `scripts/`, `data/`. Improves what the models output; never changes what shape they output.

**Lane B — Analytics & dashboard.** Owns `backend/analytics/`, `backend/routes/analytics.py`, `frontend/app/dashboard/`, chart components. Owns the density ranking screen.

**Lane C — Review workflow & intake.** Owns `backend/routes/reports.py`, `backend/routes/review.py`, `frontend/app/intake/`, `frontend/app/reports/`, `frontend/app/review/`.

**Lane D — Tier 2 & hardening.** Owns `frontend/app/trends/`, PII redaction, near-duplicate detection, `tests/`, demo seed scripts.

Cross-lane need → stop, log it in `DIY.md` as a cross-lane request, keep working on something else. Never reach into another lane's file.

## Git model

One branch per lane per day: `lane-a/day2`, `lane-b/day2`, … Push to the branch, never to `main`. The integrator reviews and merges. A lane that force-pushes, rebases `main`, or merges its own branch has broken the model.

## Day 2 — Tier 1 depth — CLOSED 2026-08-27
- [x] Lane A: real acronym dictionary (45 -> 94 applied, 11 -> 21 unverified), spellcheck tuning, expanded NER ruler (111 mined patterns, SpanRuler), error analysis on the held-out set, retrained SIF classifier
- [x] Lane B: density ranking correctness + drill-down, rule distribution chart, KPI accuracy
- [x] Lane C: confirm/override write path, review-queue filtering, intake validation and error states
- [~] Lane D: edge-case test suite from `PRD.md`, PII name redaction — **suite real and green, but PII redaction and near-duplicate detection are wired into NO production path** (`AUDIT.md` 2026-08-27). Stays `[~]` until that cross-lane decision lands.
- **[x] EXIT MET 2026-08-27, integrator-verified after force-correction.** Every lane merged to `main`.
  Verified by running, not by reading: pytest **21 passed / 1 xfailed / 0 failed**, inference
  self-check **22/22**, `npx tsc --noEmit` **0 errors**, `npx eslint .` **0 problems**,
  `npm run build` **succeeds**, `density.py` self-check passed, span invariant **81 spans /
  0 mismatches** on the real corpus through the real pipeline.
  EIGHT force-corrections were required first, all logged in `AUDIT.md` § "Day 2 corrections":
  the span-integrity test was never collected (hyphenated filename) and 3 of its 4 tests were
  passing vacuously on a wrong corpus path; `pytest` was in no requirements file and the suite
  could not run in EITHER interpreter as merged; one real tagger failure pinned as a strict
  `xfail` rather than weakened; three stale prose claims that the code contradicted.
  NOT MET and not marked met: the full flow has **never been driven through a browser** — that
  is the human's signed-in pass on the live URLs (`DIY.md`).

---

# FINAL CONSOLIDATION, INTEGRATION & DEMO FREEZE — the only remaining milestone

Days 3, 4 and 5 are **collapsed into this single milestone** as of 2026-08-27. There is no Day 3
work, no Day 4 work, and no Day 5 buffer to fall back on: the buffer has been spent on Day 2's
corrections. Anything not in the Hard Scope Lock below is cut.

## Hard Scope Lock — the demo is these four screens and nothing else

Locked 2026-08-27. All four are built and running today; this milestone hardens them, it does not
extend them. **No new feature enters this list.** A defect in one of these four outranks every
other piece of work in the repo.

1. **Intake** — submit renders the result inline, no navigation. The hero interaction.
2. **Report Detail ("Magic View")** — colour-coded precursor highlighting from real spans, verdict
   badge, confidence, IOGP chips. Span exactness verified at 81/81 spans, 0 mismatches.
3. **Density Ranking + drill-down** — the literal expected-outcome line of the problem statement.
   Wilson lower bound ordering, click a row for the reports behind its score.
4. **Review Queue** — low-confidence reports, confirm/override writing through to the database.

**Explicitly CUT, and to be described as scoped-out-on-purpose if a judge asks** (not as
unfinished): the Trends page, the simulated in-app alert, wiring PII redaction or near-duplicate
detection into the ingest path, any further model training, any Render/cloud backend deploy, and
the 1,200-row dataset target.

## Final Sprint Worklist — in this order

**1. Localhost tunnel + Vercel live verification.**
- [ ] Bring up a **named** tunnel (`cloudflared` / `localtunnel`) to the local backend on 8001. Named, because an ad-hoc URL changes on restart and `NEXT_PUBLIC_API_BASE_URL` is baked into the Vercel bundle at **build** time — a restarted tunnel then needs a redeploy, not a restart.
- [ ] Add the tunnel origin to the backend's `FRONTEND_ORIGINS`, and set `NEXT_PUBLIC_API_BASE_URL` to the tunnel host with **no trailing slash**. A trailing slash breaks the CORS match with an opaque error that looks like the API is down.
- [ ] **The signed-in browser pass, both roles, on the live URLs.** This is the single largest open gap in the project: no page has ever been rendered in a browser by an agent. Walk all four locked screens as `hse_manager` and as `site_supervisor`, and confirm the empty states and a stored injection payload render as inert text.
- [ ] **Measure and log real numbers through the tunnel** — ingest latency against the 3s target, dashboard load against the 2s target. The "~60 ms" figure behind the tunnel decision is a target, not an observation, and no measured tunnel number exists yet. Log whatever it actually is in `AUDIT.md`, including a bad result.
- Exit: all four locked screens work end to end from the Vercel URL through the tunnel, in a browser, on both roles, with measured latency logged.

**2. `FALLBACK.md` — the live-demo resilience playbook.**
- [ ] Write it for the failure modes this architecture actually has, in the order they are likely: tunnel drops mid-demo; venue network fails; laptop sleeps or the uvicorn process dies; Supabase unreachable; a submitted report returns 502.
- [ ] For each: the symptom on screen, the recovery command, and the fallback if recovery takes longer than a few seconds. The 50 pre-seeded processed reports exist precisely so Dashboard and Density stay real if live inference stalls — say so, and name the screens that keep working.
- [ ] Include the pre-demo checklist: tunnel up and reachable, backend warm (the first inference pays a ~1.4 s model load), 50 seed rows present, both demo accounts able to sign in.
- Exit: `FALLBACK.md` committed, and every recovery command in it has been **run once** rather than only written down.

**3. Team presentation rehearsal and judge Q&A drill.**
- [ ] One full dry run with zero manual workarounds, on the live stack, timed.
- [ ] Rehearse the honest answers, because the weak numbers are in the repo and a judge may find them: test accuracy **0.5918** on n=49 and what that does and does not license us to claim; separation +0.1126 against validation's +0.2662, which is overfitting on 235 rows; the tagger covers **8 of 9** IOGP rules and `Work Authorisation` has **0** training rows and is untrainable — never claim all 9; the 50/50 training balance against ~20-25% field prevalence, and that it reaches no dashboard denominator; the dataset is synthetic, localized from real OSHA narratives; the Trends page does not exist on purpose.
- [ ] **Feature freeze the moment this dry run passes.** After freeze: bug fixes to the four locked screens only.
- Exit: an unassisted end-to-end dry run succeeds on the live URLs, and every person presenting can answer the weak-number questions without improvising.

## Carried-over open items (not new work — they block a clean close)

These are already logged; they are listed here so the milestone cannot be called done around them.
Each has its full detail in `DIY.md` or `AUDIT.md`.

- [ ] `PATTERNS.md` and `README.md` still carry stale `INTERIM_LANE_A` prose. `PATTERNS.md` is FROZEN; both are integrator-only.
- [ ] Decide the 10 `interim-keyword-0.1` classification rows — one holds the project's only human `overridden` decision.
- [ ] Delete the redundant repo-root `model_weights/` (257 MB, byte-identical to the live copy) and the dead root `Dockerfile`.
- [ ] `ruff` is installed nowhere and is in no requirements file, so the backend has no linter and `CLAUDE.md` documents a command that does not run. Add it or correct `CLAUDE.md`.
- [ ] Train/serve skew: all three models were fitted on `raw_text` and are served `cleaned_text`. Unquantified. Needs an integrator call on which lane fixes it — or an explicit decision to ship as-is and say so.
