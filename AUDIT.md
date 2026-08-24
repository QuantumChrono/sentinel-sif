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
