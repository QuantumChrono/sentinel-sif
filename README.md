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
   startup. Measured: 885 MB of site-packages plus 537 MB of weights, against Render free tier's
   **512 MB** ceiling.
2. **Delivery.** `model_weights/` is in `.gitignore`, so the 513 MB of weights cannot reach Render
   by push **at all**. A Render deploy would boot healthy and then fail on the first inference
   call — worse than not deploying, because it looks fine until someone submits a report.

The laptop has the RAM and already holds the weights, so both failure modes stop existing rather
than being mitigated. The cost is that the demo now depends on the laptop and the venue network.
`FALLBACK.md` (see `STAGES.md` § Final Sprint Worklist) is where that risk is handled.

The root `Dockerfile` is **on no deploy path** — a leftover from the dropped Hugging Face Spaces
plan. Flagged for deletion in `DIY.md`.

## Running it locally

Backend. **Port 8000 is occupied by an unrelated service on this machine, so use 8001:**

```bash
cd backend
.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8001
```

Use `http://127.0.0.1:8001`, **not** `localhost:8001`, for anything you intend to time. uvicorn
binds IPv4-only while `localhost` resolves to `::1` first, so every new connection pays a failed
IPv6 attempt: `GET /health` measured 2649 ms via `localhost` against 615 ms via `127.0.0.1`. The
real pipeline cost is ~384 ms, of which inference is 5.6 ms.

Frontend:

```bash
cd frontend
npm run dev          # dev server
npm run build        # production build
npx tsc --noEmit     # typecheck — 0 errors expected
npx eslint .         # lint — 0 problems expected
```

Tests and self-checks, all from `backend/`:

```bash
.venv/Scripts/python.exe -m pytest                            # 21 passed, 1 xfailed
.venv/Scripts/python.exe -m inference.test_inference          # 22/22
.venv/Scripts/python.exe -m preprocessing.test_clean_report   # 45/45
.venv/Scripts/python.exe analytics/density.py                 # density self-check
```

The one xfail is deliberate and `strict`: the IOGP tagger cannot emit "Hot Work" because that rule
has 8 training and 0 test rows. It is pinned as a known model deficiency rather than hidden by a
weakened assertion (`DECISIONS.md` 2026-08-27).

`pytest` is pinned in **`scripts/requirements.txt`**, not `backend/requirements.txt` — the latter
is the deploy manifest and the deployed service never runs the suite. If `pytest` is missing:

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

`backend/model_weights/`, **513 MB total**, loaded lazily on first call:

| Directory | Size | What |
|---|---|---|
| `sif_classifier/` | 257 MB | Fine-tuned DistilBERT, softmax + temperature scaling from `calibration.json` |
| `iogp_tagger/` | 257 MB | 9-way **sigmoid** multi-label head |
| `precursor_ner/` | 269 KB | spaCy SpanRuler, 111 mined patterns |

Weights are **not committed** — `.gitignore` excludes `model_weights/`, `*.safetensors` and
`*.bin`. That is the delivery blocker behind the tunnel architecture above.

Every `classifications` row this build writes carries `model_version = 'distilbert-sif-1.0'`, which
is what makes the swap auditable. 10 older rows still carry `interim-keyword-0.1` and are pending a
decision in `DIY.md`.

### Honest model performance

Read these before describing the system to anyone. Full numbers in `AUDIT.md` 2026-08-27, all read
from `calibration.json` rather than a training log.

- **SIF classifier, held-out test (n=49): accuracy 0.5918, F1 0.5833.** Weak. Validation (n=42) is
  0.6905, and test separation (+0.1126) is less than half validation separation (+0.2662) — that
  gap is overfitting on 235 fitting rows, and it is the finding, not a footnote.
- It is no longer degenerate, which is the real improvement: it predicts both classes, confidences
  span 0.519–0.874, and 12 of 49 test rows fall below the 0.65 threshold — so the review queue and
  the auto-publish path are both live behaviours.
- **The IOGP tagger covers 8 of the 9 rules, not 9.** `Work Authorisation` has **0** training rows
  and is untrainable, so its output unit can only ever predict 0. Never claim all nine.
- The training corpus is balanced ~50/50 on `sif_potential` against a ~20–25% field prevalence.
  That is a training-set property only and reaches no dashboard denominator or rate.
- The dataset is **synthetic**: real OSHA Severe Injury Report narratives rewritten into Indian
  oil-rig context by an offline script. 326 localized rows, 277 train / 49 test.
