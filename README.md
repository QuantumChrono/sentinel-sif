# SentinelSIF

Serious-Injury-and-Fatality (SIF) potential screening for oil & gas HSE reports.

Project documentation lives in `PRD.md` (spec), `STAGES.md` (plan and current position),
`AGENTS.md` (agent operating rules), `PATTERNS.md` (reference implementation).

## Production architecture

All three pieces are live and were smoke-tested end to end on 2026-08-26.

| Piece | Platform | Root directory | Entry |
|---|---|---|---|
| `frontend/` | Vercel | `frontend` | Next.js, auto-detected |
| `backend/` | Render — Web Service, native Python 3 runtime | `backend` | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| database | Supabase — managed Postgres | — | provisioned in Block 2 |

Both services build from the same GitHub commit and both use **monorepo root-directory
targeting**: each platform is pointed at one subdirectory and never sees the other. Render's
build command is `pip install -r requirements.txt`, run inside `backend/`, which is why the
start command says `main:app` and not `backend.main:app`.

`$PORT` is injected by Render and is not fixed — the start command must interpolate it, and
`--host 0.0.0.0` is required because `127.0.0.1` inside the container is unreachable from
outside it.

The root `Dockerfile` is **not used by this deployment**. Render runs the native Python runtime,
not a container. The file is a leftover from the earlier Hugging Face Spaces plan (see
`DECISIONS.md` 2026-08-26) and is flagged for deletion in `DIY.md`.

## Environment variables

Names only — values are pasted by the integrator into each platform's own settings UI. Nothing
below belongs in a committed file. Templates: `backend/.env.example`, `frontend/.env.example`.

**Vercel** (Project → Settings → Environment Variables). All three are `NEXT_PUBLIC_*`, so they
are **baked into the browser bundle at build time** — changing one requires a redeploy, not a
restart, and none of them may ever hold a secret.

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — the anon/publishable key. **Never the service-role key.**
- `NEXT_PUBLIC_API_BASE_URL` — the Render service URL, `https://<service>.onrender.com`, **no
  trailing slash**: `frontend/lib/api_client.ts` builds requests as `` `${BASE_URL}${path}` ``
  where every path already starts with `/`.

**Render** (Service → Environment). Exactly three, no more.

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` — full database access, bypasses RLS. Backend only, forever.
- `FRONTEND_ORIGINS` — comma-separated allowed CORS origins, scheme + host only, no trailing
  slash and no path: `https://<project>.vercel.app`

`backend/database.py` reads the first two at **import** time, so a missing one is a `KeyError`
before uvicorn binds a port: the symptom is a failed deploy with the reason in Render's log, not
a 500 from a running app.

`GEMINI_API_KEY` and `GROQ_API_KEY` are **absent from both platforms and from `backend/.env`.**
They are read only by `scripts/localize_dataset.py`, which runs offline on a laptop and is
imported by no runtime path. The separation is deliberate: offline data generation and the
runtime backend share no credentials.

## CORS

`backend/main.py` reads `FRONTEND_ORIGINS` and defaults to `http://localhost:3000` when it is
unset. There is no wildcard and there must never be one: this API holds the service-role key, so
`allow_origins=["*"]` would let any page on the internet read and write every table through a
visitor's browser.

Two consequences worth knowing:

- **Vercel preview deployments will be blocked.** Every preview gets its own
  `https://<project>-<hash>-<team>.vercel.app` origin, and none of them is in the list. Either
  demo from the production URL only, or add the specific preview origin you intend to use.
- **A trailing slash breaks the match.** An `Origin` header is scheme + host + port, never a path,
  so `https://x.vercel.app/` is not equal to `https://x.vercel.app` and the browser will reject
  the response with an opaque CORS error that looks like the API is down.

## Model weights

**Today the service needs no weights and no ML libraries at all.** Inference is the
`INTERIM_LANE_A` keyword implementation in `backend/inference/` — plain Python and `re` — so
`backend/requirements.txt` is the entire dependency list.

Every `classifications` row this build writes carries `model_version = 'interim-keyword-0.1'`,
which is what makes the swap auditable rather than silent.

When the fine-tuned DistilBERT weights land (Block 8, Lane A), the weights **do not get committed
to this repo** — `.gitignore` already excludes `*.safetensors`, `*.bin` and `model_weights/`. The
path is a separate Hugging Face **Model** repo, pulled by id at service start, with the model id
and revision pinned as a Render environment variable. That adds `torch` and `transformers` to
`backend/requirements.txt` and a warm-up call at startup so the first user request does not pay
the load. Note that Render's free tier has a 512 MB memory ceiling, which is the constraint to
check before that swap, not disk.
