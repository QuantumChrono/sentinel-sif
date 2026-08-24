# AUDIT.md — Findings log
Format/rules: see `AGENTS.md` § Logging protocols. Real numbers only, log negative results too, newest at bottom.

---

### [Planning] Governance docs referenced a stage plan that no longer exists — 2026-08-24
Type: inconsistency | Severity: med
Finding: `AGENTS.md` and `CLAUDE.md` both pointed at stage numbers from a superseded ~16-stage plan while `STAGES.md` defined only Stages 0–4. Concrete dangling references: "Stage 10 explicitly requires removing Stage 5's mock endpoints" and "frontend/UI stages (11-14)" in `AGENTS.md`; "see Stage 16" in `CLAUDE.md`. An agent bootstrapping from these files would have looked for stages that do not exist, and the skill-routing hint ("stages 11-14") would never have matched any real stage. Status: resolved — both files rewritten against the day/lane model; all stage-number references replaced with day/block/lane references.

### [Planning] `meta_roadmap.md` is unreadable by agents by design — 2026-08-24
Type: tech-debt | Severity: low
Finding: `meta_roadmap.md` contains the human playbook, including copy-pasteable prompts intended *for* the agent. An agent that reads it would consume a large amount of context re-reading instructions it already receives directly, and could mistake a Day-3 prompt for a current instruction. Status: accepted — mitigated by an explicit "do not read `meta_roadmap.md`" line in `CLAUDE.md`. Accepted rather than resolved because nothing mechanically prevents a session from opening the file.

### [Day 1 / Block 1] Fresh Next.js scaffold shipped a critical RCE advisory — 2026-08-24
Type: security | Severity: high
Finding: `npm audit` on the untouched `create-next-app@15.5.4` output reported 3 vulnerabilities — 1 critical, 2 high. Critical was GHSA-9qr9-h5gf-34mp (RCE in the React flight protocol) against `next` 9.3.4-canary.0 – 16.3.0-preview.10. Resolved by pinning `next@15.5.23`; re-audit shows 0 critical. Status: resolved

### [Day 1 / Block 1] Three high advisories remain, all transitive via `sharp` — 2026-08-24
Type: security | Severity: med
Finding: post-upgrade `npm audit` reports 3 high advisories, all in `sharp` <0.35.0 (libvips CVE-2026-33327, CVE-2026-33328, CVE-2026-35590, CVE-2026-35591), reached only as an optional dependency of `next`. `npm audit fix --force` resolves them solely by installing `next@16.3.2`, a major-version change. `sharp` is used by the `next/image` optimizer; the app currently renders no images. Status: accepted — re-evaluate at Day 4 hardening, and before any `next/image` use on untrusted input.

### [Day 1 / Block 1] Port 8000 already occupied locally — first /health check was a false pass — 2026-08-24
Type: bug | Severity: med
Finding: the first `uvicorn main:app --port 8000` verification returned HTTP 200 with `{"status":"healthy","timestamp":"...","version":"2.4.dev.13"}` — not this codebase's response. `main.py` returns `{"status":"ok"}` and nothing else, and the uvicorn log was empty. An unrelated process (PID 20396, "Kiro Gateway", an Amazon Q/CodeWhisperer proxy) holds 0.0.0.0:8000, so uvicorn never bound and curl hit the wrong server. Re-ran on port 8010: `/health` → `{"status":"ok"}` HTTP 200, and `/openapi.json` reports `"title":"SentinelSIF API"`, confirming our app served it. Status: resolved — verify backend on 8010 locally, or confirm `openapi.json` identity before trusting a `/health` 200.

### [Day 1 / Block 1] Root .gitignore was ignoring the .env.example templates it was meant to keep — 2026-08-24
Type: bug | Severity: high
Finding: the pre-existing root `.gitignore` had `.env.*` with no negation, so `git check-ignore` matched both `frontend/.env.example` and `backend/.env.example` — the two files Block 1 must commit would have been silently untracked, leaving teammates with no variable manifest. It also ignored `data/**/*.csv` and `data/processed/` but not `data/raw/`, and had no rule preserving the `data/raw/SOURCE.md` that Block 3 requires committed. Rewritten with `!.env.example` and per-directory `data/*` + `!data/*/*.md` negations. Verified with `git check-ignore -v`: the three template/provenance paths are now tracked; `node_modules/`, `.venv/`, `.env`, and `data/raw/January2015toNovember2025.csv` are ignored. Status: resolved

### [Day 1 / Block 1] Scaffold exit criteria verified — 2026-08-24
Type: test-result | Severity: low
Finding: backend — `uvicorn main:app --port 8010` → `GET /health` returns `{"status":"ok"}` HTTP 200, app identity confirmed via `openapi.json` title `SentinelSIF API`. Frontend — `npm run dev` (port 3010) returns HTTP 200, `<title>SentinelSIF</title>`, Tailwind stylesheet linked at `/_next/static/css/app/layout.css`; grep for `next.svg`, `vercel.svg`, `Create Next App`, `Get started by editing` returns zero matches, confirming demo content is gone. `npm run lint` clean, `npx tsc --noEmit` clean. Status: resolved

### [Day 1 / Block 2] `backend/.env` contains the frontend variables, not the backend ones — 2026-08-24
Type: bug | Severity: high
Finding: `backend/.env` holds exactly three keys — `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL` — byte-identical in key set and value lengths to `frontend/.env.local` (40 / 208 / 21 chars). It is a copy of the frontend file. None of the four keys `backend/.env.example` declares (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `FRONTEND_ORIGINS`) are present, so importing `backend/database.py` raises `KeyError: 'SUPABASE_URL'`. Confirmed by reading key names and value lengths only — no secret value was printed. Consequence: the anon key, not the service-role key, is what is currently on disk for the backend; the backend cannot reach the DB at all until a human supplies the real service-role key. Status: open — logged in `DIY.md`, blocks the Block 2 insert/select verification.

### [Day 1 / Block 2] `ruff` is not installed, so the documented backend lint command does not run — 2026-08-24
Type: tech-debt | Severity: low
Finding: `CLAUDE.md` names `ruff check .` as the backend lint command and `AGENTS.md` requires lint to pass before exit criteria are met, but `python -m ruff --version` reports "No module named ruff" and `ruff` appears in neither `requirements.txt` nor the venv. No backend lint has been run on any block so far, Block 1 included; the Block 1 exit note recorded only the frontend `npm run lint` and `tsc` passes. `backend/database.py` and `backend/main.py` are therefore unlinted, not lint-clean. Status: open — install `ruff` (pinned) before the next block that writes Python, and do not record a backend lint pass until it actually runs.

### [Day 1 / Block 2] Seed coordinates verified against OpenStreetMap; three candidate sites dropped — 2026-08-24
Type: metric | Severity: low
Finding: all 8 seeded `sites` coordinates were looked up live via the OpenStreetMap Nominatim search API on 2026-08-24 and rounded to 5 dp; none came from model memory. Six resolved to settlement records (`place` class): Duliajan 27.35591/95.31923 (town), Naharkatiya 27.28630/95.32583 (town), Moran 27.18574/94.91043 (town), Baghjan 27.60628/95.40450 (hamlet, "Baghjan Gaon"), Makum 27.48454/95.43813 (town), Tanot 27.79601/70.35316 (village), Ramgarh 27.37291/70.49667 (village) — that is seven; the eighth, Hapjan 27.50013/95.42785, resolved only to a POI (Hapjan PHC, `healthcare` class), as OSM holds no settlement record for it, and is marked `poi` in the schema comment. Three further OIL area names returned zero Nominatim results and were dropped rather than assigned invented coordinates: Dandewala, Bagitibba, Jorajan. Separately: the coordinates are verified, but the claim that each locality is an *OIL operating area* is not — `WebSearch` returned HTTP 500 for the whole session, so that association rests on unverified model knowledge. Status: open — a human should confirm the operating-area list against an OIL source before these names appear in the demo.
