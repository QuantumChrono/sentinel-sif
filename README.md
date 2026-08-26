---
title: SentinelSIF API
emoji: 🛡️
colorFrom: gray
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# SentinelSIF

Serious-Injury-and-Fatality (SIF) potential screening for oil & gas HSE reports.
Frontend: Next.js on Vercel. Backend: FastAPI in this container. Database: Supabase managed Postgres.

**The YAML block above is Hugging Face Spaces configuration, not decoration.** A Space reads it
from the README at its repo root; `sdk: docker` selects the root `Dockerfile` and `app_port: 7860`
must match the `--port` in that Dockerfile's `CMD`. Change one and you change both.

Project documentation lives in `PRD.md` (spec), `STAGES.md` (plan and current position),
`AGENTS.md` (agent operating rules), `PATTERNS.md` (reference implementation).

## Deployment layout

| Piece | Platform | Root | Entry |
|---|---|---|---|
| `frontend/` | Vercel | `frontend` (set as Root Directory) | Next.js, auto-detected |
| `backend/` | HF Spaces (docker SDK) | repo root | root `Dockerfile` → `uvicorn main:app --port 7860` |
| database | Supabase | — | already provisioned |

Both platforms build from the same commit, but they get it differently. **Vercel** connects to
the GitHub repo and is pointed at `frontend/` as its Root Directory. **A Space is its own git
repo** — it does not read GitHub — so this repo gets a second remote and is pushed to it:

    git remote add space https://huggingface.co/spaces/<owner>/<space>
    git push space main

That is a push to a *different remote*, so the `main`-branch protection on GitHub is untouched.
The Space then builds the root `Dockerfile`, which copies only `backend/`.

## Environment variables

Names only — values are pasted by the integrator into each platform's own settings UI. Nothing
below belongs in a committed file. Templates: `backend/.env.example`, `frontend/.env.example`.

**Vercel** (Project → Settings → Environment Variables). All three are `NEXT_PUBLIC_*`, so they
are **baked into the browser bundle at build time** — changing one requires a redeploy, not a
restart, and none of them may ever hold a secret.

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the anon/publishable key. **Never the service-role key.**
- `NEXT_PUBLIC_API_BASE_URL` — the Space URL, `https://<owner>-<space>.hf.space`, **no trailing
  slash**: `frontend/lib/api_client.ts` builds requests as `` `${BASE_URL}${path}` `` where every
  path already starts with `/`.

**Hugging Face Space** (Settings → Variables and secrets → all three as *Secrets*).

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — full database access, bypasses RLS. Backend only, forever.
- `FRONTEND_ORIGINS` — comma-separated allowed CORS origins, scheme + host only, no trailing
  slash and no path: `https://<project>.vercel.app`

`GEMINI_API_KEY` and `GROQ_API_KEY` are **deliberately absent from both platforms**. They are read
only by `scripts/localize_dataset.py`, which runs offline on a laptop and is never imported by any
runtime path. Pasting them into a deployed service would put a paid credential in a public
container for nothing.

## CORS

`backend/main.py` reads `FRONTEND_ORIGINS` and defaults to `http://localhost:3000` when it is
unset. There is no wildcard and there must never be one: this API holds the service-role key, so
`allow_origins=["*"]` would let any page on the internet read and write every table through a
visitor's browser.

Two consequences worth knowing before the first deploy:

- **Vercel preview deployments will be blocked.** Every preview gets its own
  `https://<project>-<hash>-<team>.vercel.app` origin, and none of them is in the list. Either
  demo from the production URL only, or add the specific preview origin you intend to use.
- **A trailing slash breaks the match.** An `Origin` header is scheme + host + port, never a path,
  so `https://x.vercel.app/` is not equal to `https://x.vercel.app` and the browser will reject
  the response with an opaque CORS error that looks like the API is down.

## Model weights

**Today the container needs no weights and no ML libraries at all.** Inference is the
`INTERIM_LANE_A` keyword implementation in `backend/inference/` — plain Python and `re` — so
`backend/requirements.txt` is the entire dependency list and the image is a `python:3.11-slim`
with FastAPI and the Supabase client on top. Nothing about this deploy waits on Block 8.

Every `classifications` row this build writes carries `model_version = 'interim-keyword-0.1'`,
which is what makes the swap auditable rather than silent.

When the fine-tuned DistilBERT weights do land (Block 8, Lane A), the weights **do not get
committed to this repo** — `.gitignore` already excludes `*.safetensors`, `*.bin` and
`model_weights/`, and a Space git repo is the wrong place for a few hundred MB. The path is a
separate Hugging Face **Model** repo, pulled by id at container start, with the model id and
revision pinned as a Space secret. That adds `torch` and `transformers` to
`backend/requirements.txt` and a warm-up call at startup so the first user request does not pay
the load. None of it is built yet, on purpose: there are no weights to point at.
