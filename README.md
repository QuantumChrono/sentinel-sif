# SentinelSIF

Serious-Injury-and-Fatality (SIF) potential screening for oil & gas HSE reports.

Project documentation lives in `PRD.md` (spec), `STAGES.md` (plan and current position),
`AGENTS.md` (agent operating rules), `PATTERNS.md` (reference implementation).

## Production architecture — CHANGED 2026-08-27

| Piece | Platform | Root directory | Entry |
|---|---|---|---|
| `frontend/` | Vercel | `frontend` | Next.js, auto-detected |
| `backend/` | **The integrator's laptop, exposed by a secure tunnel** | `backend` | `uvicorn main:app --port 8001` |
| database | Supabase — managed Postgres | — | provisioned in Block 2 |

**Render is retired as the backend host.** It was live and smoke-tested on 2026-08-26, but the
Block 8 weight swap made it unusable for two measured reasons, neither fixable by configuration
(`DECISIONS.md` 2026-08-27):

1. **Memory.** `backend/inference/` imports `torch`, `transformers` and `spacy` at module load, so
   they are in `backend/requirements.txt` and cannot be removed without every endpoint failing at
   startup. Measured: 885 MB of site-packages plus 514 MB of weights, against Render free tier's
   **512 MB** ceiling.
2. **Delivery.** `model_weights/` is in `.gitignore`, so the 514 MB of weights could not reach Render
   by push **at all**. A Render deploy would boot healthy and then fail on the first inference
   call — worse than not deploying, because it looks fine until someone submits a report.
   *Superseded in part on 2026-08-28:* the Hugging Face auto-download (quickstart step 3) now solves
   delivery on any host. **Memory alone still rules Render out**, so the decision stands unchanged.

The laptop has the RAM and already holds the weights, so both failure modes stop existing rather
than being mitigated. The cost is that the demo now depends on the laptop and the venue network.
`FALLBACK.md` (see `STAGES.md` § Final Sprint Worklist) is where that risk is handled.

The root `Dockerfile` is **on no deploy path** — a leftover from the dropped Hugging Face Spaces
plan. Flagged for deletion in `DIY.md`.

## Getting started — local setup in 5 minutes

Nothing needs to be trained or hand-copied. Model weights arrive on their own in step 3.

**1 — Clone.**

```bash
git clone https://github.com/QuantumChrono/sentinel-sif && cd sentinel-sif
```

**2 — Environment files.** Copy both templates, then paste the Supabase values in. Ask the integrator
for the keys; they are in no committed file.

```bash
cp backend/.env.example  backend/.env
cp frontend/.env.example frontend/.env.local
```

`backend/.env` takes three: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`FRONTEND_ORIGINS=http://localhost:3000`.
`frontend/.env.local` takes three: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and
`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001` — **no trailing slash**.

`backend/database.py` reads the first two at **import** time, so a missing one stops uvicorn before
it binds a port, with the reason in the log — not a 500 from a running app.

**3 — Model weights: automatic, no action needed.** `backend/model_weights/` is 514 MB and
`.gitignore`d, so a fresh clone contains none of it. `backend/main.py` checks for
`model_weights/sif_classifier/model.safetensors` at import and, if it is absent, pulls the whole set
from the Hugging Face Hub repo `swayamohapatra/sentinel-sif`. First start therefore downloads
~514 MB and takes a few minutes; every later start skips the check in milliseconds. To fetch ahead
of time, or to re-fetch after deleting the directory:

```bash
python scripts/download_model_weights.py
```

Both paths read `HF_MODEL_REPO` if you need a different repo. This is what routes around GitHub's
100 MB per-file limit — the two DistilBERT checkpoints are 257 MB each.

**4 — Backend.** **Port 8000 is occupied by an unrelated service on this machine, so use 8001:**

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Git Bash on Windows
# PowerShell:  .venv\Scripts\Activate.ps1        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

`pip install` pulls ~885 MB of site-packages, `torch` being most of it. On Linux, install torch from
PyTorch's CPU index first (`pip install --index-url https://download.pytorch.org/whl/cpu
torch==2.11.0`) or pip resolves a multi-gigabyte CUDA build that is pointless on a CPU-only host.

**5 — Frontend.**

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

**Optional — remote or mobile demo.** Expose the local backend through a tunnel and point the
deployed frontend at it:

```bash
npx cloudflared tunnel --url http://127.0.0.1:8001
```

Then set Vercel's `NEXT_PUBLIC_API_BASE_URL` to the printed hostname and **redeploy** — it is baked
in at build time — and add that same origin to the backend's `FRONTEND_ORIGINS`. Neither value may
carry a trailing slash. Details and the stable named-tunnel setup are in the next section.

### One local caveat worth knowing

Use `http://127.0.0.1:8001`, **not** `localhost:8001`, for anything you intend to time. uvicorn binds
IPv4-only while `localhost` resolves to `::1` first, so every new connection pays a failed IPv6
attempt: `GET /health` measured 2649 ms via `localhost` against 615 ms via `127.0.0.1`. The real
pipeline cost is ~384 ms, of which inference is 5.6 ms.

### Checks

Frontend, from `frontend/`:

```bash
npm run build        # production build
npx tsc --noEmit     # typecheck — 0 errors expected
npx eslint .         # lint — 0 problems expected
```

Backend, from `backend/`:

```bash
.venv/Scripts/python.exe -m pytest                            # 21 passed, 1 xfailed
.venv/Scripts/python.exe -m inference.test_inference          # 22/22
.venv/Scripts/python.exe -m preprocessing.test_clean_report   # 45/45
.venv/Scripts/python.exe analytics/density.py                 # density self-check
```

The one xfail is deliberate and `strict`: the IOGP tagger cannot emit "Hot Work" because that rule
has 22 training and 2 test rows. It is pinned as a known model deficiency rather than hidden by a
weakened assertion (`DECISIONS.md` 2026-08-27).

`pytest` is pinned in **`scripts/requirements.txt`**, not `backend/requirements.txt` — the latter is
the deploy manifest and the deployed service never runs the suite. If `pytest` is missing:

```bash
backend/.venv/Scripts/python.exe -m pip install pytest==9.1.1
```

**There is no backend linter.** `ruff` is installed in neither the venv nor either requirements
file, so the `ruff check .` command documented in `CLAUDE.md` does not run. Stated here rather than
left to be discovered.

## Exposing the backend with a tunnel

Either tool works. Prefer a **named** tunnel:

```bash
# Cloudflare — quick (ephemeral URL, changes on every restart)
cloudflared tunnel --url http://127.0.0.1:8001

# Cloudflare — named (stable hostname, survives restarts; do this before the demo)
cloudflared tunnel login
cloudflared tunnel create sentinel-sif
cloudflared tunnel route dns sentinel-sif <your-hostname>
cloudflared tunnel run --url http://127.0.0.1:8001 sentinel-sif

# localtunnel alternative
npx localtunnel --port 8001
```

Two things break the moment the tunnel URL changes, and both are build-time, not runtime:

- `NEXT_PUBLIC_API_BASE_URL` is **baked into the Vercel bundle at build time**, so a new tunnel URL
  needs a **redeploy**, not a restart. This is the reason to use a named tunnel.
- The tunnel origin must be added to the backend's `FRONTEND_ORIGINS`, and neither value may carry
  a **trailing slash** — an `Origin` header is scheme + host + port and never a path, so
  `https://x.example.com/` does not match `https://x.example.com` and the browser reports an opaque
  CORS error that looks like the API is down.

No latency figure has been measured through a tunnel yet. The only measured numbers in this repo
are local (above); anything else is a target, not an observation.

## How a report flows

```
browser (Vercel)                    integrator's laptop                Supabase
+------------------+                +---------------------+            +-----------+
| Next.js frontend | --- HTTPS ---> |  FastAPI :8001      | --- SQL -> | Postgres  |
|  /intake         |    tunnel      |                     |            |  reports  |
|  /dashboard      |                |  1 clean_report     |            |  classi-  |
|  /review         | <--- JSON ---- |  2 classify_sif     | <--------- |  fications|
|  /reports/[id]   |                |  3 tag_iogp_rules   |            |  precur-  |
+------------------+                |  4 extract_precurs. |            |  sors     |
                                    +---------------------+            +-----------+
                                       weights loaded lazily from
                                       backend/model_weights/ (514 MB,
                                       auto-pulled from Hugging Face)
```

`POST /api/v1/reports` runs all four stages **synchronously** and returns the finished verdict in one
response — there is no queue and no polling. Measured end to end at ~384 ms locally, of which
inference is 5.6 ms. Each stage is one module under `backend/inference/` or
`backend/preprocessing/`, called in the order shown by `backend/routes/reports.py`.

## The four core screens

Auth is Supabase, at `/login`; role comes from `app_metadata` via `frontend/lib/user_role.ts`.

| Route | Screen | What it does |
|---|---|---|
| `/intake` | **Submit a safety report** | Site selector plus the narrative box. On submit it `POST`s once and renders the verdict inline — SIF flag, confidence, IOGP tags and highlighted precursor spans — so the reporter sees the classification without leaving the page. |
| `/dashboard` | **HSE dashboard** | KPI cards, the SIF-precursor density ranking by site and activity (Wilson lower bound, so a 1-of-1 site cannot outrank a 40-of-90 one), the 9-rule distribution chart including zeros, and a high-risk feed. Clicking a density row opens the drill-down modal with the underlying reports. |
| `/review` | **Manual review queue** | Every report whose confidence fell below the 0.65 threshold — 53 of 252 on the held-out test, so this screen is always populated. An HSE officer confirms or overrides the model verdict, which writes back to `classifications`. |
| `/reports/[id]` | **Report detail** | Raw and cleaned text side by side, the verdict with its confidence, all IOGP tags, and every precursor span highlighted in place. Also carries the confirm/override control, so a review can be done from the detail view as well as the queue. |

## API endpoints

All eight, verified present in the live OpenAPI schema. `/docs` serves the interactive spec.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/reports` | Ingest one report, run the full pipeline synchronously, return the result |
| GET | `/api/v1/reports` | List and filter: `site_id`, `activity`, `sif_potential`, `iogp_rule`, `review_status`, `submitted_from`, `submitted_to`, `limit` |
| GET | `/api/v1/reports/{report_id}` | Full detail: raw and cleaned text, classification, tags, precursor spans |
| POST | `/api/v1/reports/{report_id}/review` | HSE officer confirms or overrides a classification |
| GET | `/api/v1/analytics/density` | SIF-precursor density ranked by site and activity (Wilson lower bound) |
| GET | `/api/v1/analytics/rules` | Report counts across all 9 IOGP rules, including zeros |
| GET | `/api/v1/analytics/review-queue` | Reports below the confidence threshold |
| GET | `/api/v1/sites` | Sites, for the intake selector |
| GET | `/health` | `{"status":"ok"}` |

`GET /api/v1/reports` returns full `ReportDetail` objects, not the narrower `ReportSummary` — Lane
B's drill-down needs precursor spans without a second request per row. `ReportSummary` remains the
documented narrow shape and the supertype the frontend types mirror, but no endpoint returns it
(`DECISIONS.md` 2026-08-27).

## Environment variables

Names only — values are pasted by the integrator into each platform's settings UI. Nothing below
belongs in a committed file. Templates: `backend/.env.example`, `frontend/.env.example`.

**Vercel** (Project → Settings → Environment Variables). All three are `NEXT_PUBLIC_*`, so they are
baked into the browser bundle at build time — changing one requires a redeploy, and none of them
may ever hold a secret.

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the anon/publishable key. **Never the service-role key.**
- `NEXT_PUBLIC_API_BASE_URL` — the tunnel hostname, **no trailing slash**:
  `frontend/lib/api_client.ts` builds requests as `` `${BASE_URL}${path}` `` and every path already
  starts with `/`.

**Backend** (`backend/.env` locally). Exactly three, no more.

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — full database access, bypasses RLS. Backend only, forever.
- `FRONTEND_ORIGINS` — comma-separated allowed CORS origins, scheme + host only, no trailing slash
  and no path.

`backend/database.py` reads the first two at **import** time, so a missing one is a `KeyError`
before uvicorn binds a port — the failure is a process that never starts, with the reason in the
log, not a 500 from a running app.

`GEMINI_API_KEY` and `GROQ_API_KEY` are **absent from `backend/.env` and from every platform.** They
are read only by `scripts/localize_dataset.py`, which runs offline and is imported by no runtime
path. The separation is deliberate: a leak of the backend's environment exposes no LLM billing, and
a leak of the laptop's exposes no database.

## CORS

`backend/main.py` reads `FRONTEND_ORIGINS` and defaults to `http://localhost:3000` when unset.
There is no wildcard and there must never be one: this API holds the service-role key, so
`allow_origins=["*"]` would let any page on the internet read and write every table through a
visitor's browser.

**Vercel preview deployments are blocked by design.** Every preview gets its own
`https://<project>-<hash>-<team>.vercel.app` origin and the allowlist holds only the origins you
name. Demo from the production URL, or add the one specific preview origin you intend to use.

## Model weights

The service loads **real fine-tuned weights**. The interim keyword implementation is gone — `grep`
finds 0 occurrences of `INTERIM_LANE_A` in any `.py`, `.ts` or `.tsx` under `backend/` or
`frontend/`.

`backend/model_weights/`, **514 MB total**, loaded lazily on first call:

| Directory | Size | What |
|---|---|---|
| `sif_classifier/` | 257 MB | Fine-tuned DistilBERT, softmax + temperature scaling from `calibration.json` |
| `iogp_tagger/` | 257 MB | 9-way **sigmoid** multi-label head |
| `precursor_ner/` | 1.6 MB | spaCy SpanRuler, 374 mined patterns |

Weights are **not committed** — `.gitignore` excludes `model_weights/`, `*.safetensors` and
`*.bin`. That is the delivery blocker behind the tunnel architecture above, and the reason for the
Hugging Face auto-download in step 3 of the quickstart.

Every `classifications` row this build writes carries `model_version = 'distilbert-sif-1.0'`, which
is what makes the swap auditable. 10 older rows still carry `interim-keyword-0.1` and are pending a
decision in `DIY.md`.

### Honest model performance

Read these before describing the system to anyone. Numbers below are the 1,688-row build, read from
`calibration.json` and `tagger_metrics.json` rather than a training log. Full per-rule detail in
`AUDIT.md`; single-report adversarial probes in the Day 3 stress-test entry there.

- **SIF classifier, held-out test (n=252): accuracy 0.7460, F1 0.7217** (precision 0.7281, recall
  0.7155; confusion TN 105 / FP 31 / FN 33 / TP 83). Validation (n=214) F1 is 0.7404, so validation
  and test now agree — the overfitting gap of the earlier 326-row build is gone.
- Calibrated with temperature 1.400 fit on validation: test ECE 0.0770, mean confidence 0.7567, and
  **53 of 252** test rows fall below the 0.65 threshold — so the review queue and the auto-publish
  path are both live behaviours, not dead branches.
- **Do not claim the IOGP tagger covers all 9 rules.** All 9 now have training rows, but macro-F1
  **0.5341** is computed over only the **6** rules with test support ≥ 3. `Confined Space` (8 train),
  `Hot Work` (22 train) and `Work Authorisation` (2 train) each score **F1 0.0000** and are
  unreliable. Micro-F1 0.5784, tag threshold 0.20.
- Precursor extraction is a SpanRuler, not a learned NER: 374 mined patterns, and barrier recall is
  structurally bounded at **102 of 235** barriers by the entailment-only policy — a barrier that is
  implied but not stated is never extracted, by design.
- Training balance is 658 positive / 778 negative (**45.8%** positive) against a ~20–25% field
  prevalence. That is a training-set property only and reaches no dashboard denominator or rate.
- The dataset is **synthetic**: real OSHA Severe Injury Report narratives rewritten into Indian
  oil-rig context by an offline script. **1,688 rows** — 1,436 in the train file (1,222 fit / 214
  validation) and 252 held-out test.
- Two known boundary failures, both training-data gaps rather than code bugs, both open: housekeeping
  reports that merely mention tools trip false-positive SIF, and a silent H2S release is
  confidently missed. State the gas blindspot out loud in any demo Q&A about atmospheric hazards.
