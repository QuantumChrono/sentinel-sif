# FALLBACK.md — Demo Resilience & Fallback Playbook

One page. Read it once before the demo, not during. Local ports: **frontend 3000**, **backend 8001** (`NEXT_PUBLIC_API_BASE_URL=http://localhost:8001`).

## Pre-demo checklist (T-15 minutes)

- [ ] **Backend up and warm.** From `backend/`: `.venv\Scripts\activate` then `uvicorn main:app --reload --port 8001`. Hit `http://127.0.0.1:8001/health` — expect `{"status":"ok"}`. If a 200 comes back with any *other* body, something else owns the port (this has happened before — see `AUDIT.md`, port 8000 / Kiro Gateway).
- [ ] **Model weights loaded, first inference done.** Submit one throwaway report so the transformers are in memory. Cold-start inference is slow enough to look broken on stage.
- [ ] **Frontend up.** From `frontend/`: `npm run dev` → `http://localhost:3000`.
- [ ] **50 seeded reports present on the Dashboard.** Count them. An empty dashboard is the worst possible opening slide.
- [ ] **Both accounts logged in and tested** — Supervisor and Manager — each in its own browser profile or window, so no mid-demo login. Confirm the Manager sees the review queue and the Supervisor does not.
- [ ] **Backups open in background tabs:** screenshot deck and the recorded walkthrough video.

## Scenario A — Cloudflare tunnel drops mid-demo

Symptom: the public URL 502s or hangs; local still fine.

1. Restart the tunnel: `npx cloudflared tunnel --url http://127.0.0.1:8001`
2. **The URL changes.** `NEXT_PUBLIC_*` is read at dev-server start, so after editing `frontend/.env.local` you must restart `npm run dev` for the new tunnel URL to take effect.
3. Faster than either: **stop using the tunnel.** Switch the browser to `http://localhost:3000` with the backend at `http://127.0.0.1:8001` and carry on. Nothing in the demo needs to be publicly reachable — the tunnel is a convenience for remote viewers, not a dependency.

## Scenario B — Venue WiFi dies

Run 100% offline on the laptop. Frontend, backend, and both models are local; inference does not call out. The only network dependency is Supabase (auth + report storage) — if that is unreachable, do not fight it: go to Scenario C and present from the seeded data and screenshots. Do not attempt a live submit while offline; a hung request on screen costs more than the demo point it was meant to make.

## Scenario C — Total system freeze

Stop trying to fix it in front of the room. Say "let me show you the results from the seeded set" and:

1. Present from the **pre-seeded 50 reports on the Dashboard** if any part of the UI is still responsive.
2. Otherwise switch to the **screenshot deck**, then the **recorded video** for the live-submit flow.
3. Keep talking through the analysis while it recovers — the classifier's reasoning is the story, the UI is only the delivery.

## If asked about a failure case

Answer straight, don't improvise a defence. The two known misses are in `AUDIT.md` § Day 3: **housekeeping false positives** (industrial tool nouns push clean reports over threshold) and the **H2S / atmospheric blindspot** (86.7% No SIF on a silent gas leak — the training corpus encodes energy as impact, fall, and crush). Both are training-data gaps with named fixes. Volunteering them lands better than being caught by them.
