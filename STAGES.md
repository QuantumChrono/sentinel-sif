# STAGES.md — Execution plan, current position, and lane ownership

This file is the single source of truth for **where the project is** and **what the current session is allowed to touch**. Read the "Current Position" block first, every session, before anything else.

Status marks: `[ ]` not started · `[~]` in progress · `[x]` done and verified. Never mark `[x]` from memory — only after actually running the exit check.

---

## Current Position

```
DAY:        Day 0 — Setup
MODE:       A (sequential, solo)
ACTIVE:     Block 0 — accounts, credentials, repo
NEXT:       Day 1 Block 1 — scaffold
INTEGRATOR: Swayam (sole owner of merges and FROZEN files)
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
- [ ] `backend/preprocessing/` — acronym expansion, spellcheck, Hinglish normalization, in that order
- [ ] Graceful degradation: low normalization confidence returns the original text and flags `language_detected`. Never throws, never silently corrupts input.
- [ ] Run against 10 hand-picked messy samples, log before/after in `AUDIT.md`
- Do NOT: import any transformer model here, make network calls, guess at OIL acronyms without noting them as unverified
- Exit: 10/10 samples processed without exception; garbage input returns something safe

## Block 5 — API contract freeze + inference interface
- [ ] Pydantic request/response models for all 7 `PRD.md` endpoints in `backend/schemas.py` — **this file becomes FROZEN for Days 2–4**
- [ ] Inference interface signatures fixed now, implementation swappable later:
      `classify_sif(text) -> (bool, float)` · `tag_iogp_rules(text) -> list[(rule_name, float)]` · `extract_precursors(text) -> list[(entity_type, entity_text, span_start, span_end)]`
- [ ] Day-1-only interim implementations behind those exact signatures so the frontend can be built against real response shapes before weights exist
- Do NOT: build the 7 endpoints twice (no separate mock-JSON pass — the frozen Pydantic contract *is* the contract), change a signature after the frontend starts consuming it
- Exit: `POST /api/v1/reports` returns a fully-shaped real response, written to all tables, with the interim implementation
- **Required `DECISIONS.md` entry:** interim implementation is scaffolding, deleted in Block 8, never a silent runtime fallback

## Block 6 — Training (background job starts here)
- [ ] Fine-tune DistilBERT SIF classifier (binary + confidence) on the Block 3 split
- [ ] Fine-tune IOGP tagger — 9-way **sigmoid** multi-label head, not softmax
- [ ] spaCy entity ruler seeded from the labeling schema
- Do NOT: touch the test split during training, tune the threshold on test data, report a metric you didn't compute
- Exit: real held-out metrics (accuracy, precision, recall, confusion matrix, per-rule F1) logged in `AUDIT.md` — no rounding up, negative results logged too

## Block 7 — Frontend (hands-on, while Block 6 runs)
- [ ] Supabase Auth + role-based redirect: `hse_manager` → Dashboard, `site_supervisor` → Intake. Verify both roles actually land correctly.
- [ ] Intake page — submit renders result **inline, no navigation**. This is the demo's hero interaction; it must feel instant.
- [ ] Report Detail "Magic View" — color-coded entity highlighting from real spans, verdict badge, confidence, IOGP chips
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
- [ ] ~50 pre-seeded processed reports (demo-day network-lag fallback)
- [ ] `PRD.md` edge-case table run against the real running system — one pass/fail line per case in `AUDIT.md`
- [ ] **`PATTERNS.md` written** — the reference implementation index: how a route is written, how a page fetches, how errors surface, how a migration is added, naming conventions, and the file-ownership map below. Every Day 2–4 session reads this instead of re-deriving conventions.
- [ ] Deploy: frontend → Vercel, backend → Render/Railway/HF Spaces. Full flow tested on deployed URLs, not just localhost.
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

## Day 2 — Tier 1 depth
- [ ] Lane A: real acronym dictionary, spellcheck tuning, expanded NER ruler, error analysis on the held-out set
- [ ] Lane B: density ranking correctness + drill-down, rule distribution chart, KPI accuracy
- [ ] Lane C: confirm/override write path, review-queue filtering, intake validation and error states
- [ ] Lane D: edge-case test suite from `PRD.md`, PII name redaction
- Exit: every lane's work merged to `main`, `main` still passes the full login → submit → dashboard flow

## Day 3 — Tier 2 + integration
- [ ] Lane A: threshold re-tune on real reviewed data, per-rule F1 improvement logged
- [ ] Lane B: dashboard load under 2s with full seeded dataset (measured, logged)
- [ ] Lane C: full role-based access verified, both roles end to end
- [ ] Lane D: Trends page — labeled "illustrative, synthetic data only," never framed as forecasting. Simulated in-app alert only, never a real SMS/WhatsApp call.
- Exit: all Tier 1 solid, Tier 2 additions labeled honestly, `main` green

## Day 4 — Hardening, deploy, rehearsal
- [ ] Every `PRD.md` edge case re-run on the **deployed** system, one pass/fail line each in `AUDIT.md`
- [ ] Non-functional requirements measured on deployed URLs: inference under 3s, dashboard under 2s
- [ ] Full demo dry run with zero manual workarounds
- [ ] **Feature freeze end of day.** After freeze: bug fixes only.
- Exit: unassisted end-to-end dry run succeeds on deployed URLs

## Day 5 — Buffer
Nothing scheduled. If Day 5 has planned work in it, the plan has already failed.
