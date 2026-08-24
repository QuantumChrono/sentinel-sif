# DIY.md — Manual tasks for Swayam (human-only)
Format/rules: see `AGENTS.md` § Logging protocols. Check "Pending" before each session; move to "Done" (with date) once **you** have confirmed it, not when an agent assumes it.

Cross-lane requests (Days 2–4) also land here: when a lane needs a change inside another lane's file, it logs the ask here instead of reaching across. The integrator resolves them.

---

## Pending — Day 0 (do all of these before Day 1 starts; Day 1 stalls without them)

- [x] **(Day 0)** Create the GitHub repo, add all four teammates as collaborators with push access, note the remote URL.
- [ ] **(Day 0)** Protect `main`: require a PR to merge, no direct pushes. This is what makes the lane model hold.
- [x] **(Day 0)** Create the Supabase project. Record project URL, anon key, and service-role key. **Service-role key is backend-only — never in any `frontend/` env var or client bundle.**
- [x] **(Day 0)** LLM API key for the offline localization script (Claude or GPT — pick one, note cost/rate-limit reasoning in `DECISIONS.md`). Confirm the key works with one throwaway call before Day 1. Edit: I picked Gemini API key.
- [x] **(Day 0)** Confirm GPU access for fine-tuning: Kaggle (T4, ~30h/week free) or Colab. Log in, start a throwaway session, confirm you actually get a GPU allocated — do this on Day 0, not at hour 6 of Day 1.
- [x] **(Day 0)** Confirm OSHA SIR data reaches your machine (direct download or Kaggle mirror + login). If the agent's sandboxed network can't fetch it, you download it manually and drop it in `data/raw/`.
- [x] **(Day 0)** Local toolchain present: Node 20+, Python 3.11+, git, `uv` or `venv`. Verify each with a version command.
- [x] **(Day 0)** Vercel account (frontend) + Render/Railway/HF Spaces account (backend). Create them now; connect billing if required. Deploying for the first time at 2am on Day 1 is where this plan dies. Chose HF Spaces.

## Pending — Days 1–4

- [ ] **(Day 1)** Decide the real `sif_potential` labeling rule with your own eyes on the OSHA severity columns, before the agent generates a single label. This is a judgment call, not an agent task — it is the one thing a judge is most likely to interrogate.
- [ ] **(Day 1)** Manually read ~20 localized narratives before the full 2,000-row generation runs. You are checking that they sound like Indian oil-rig reports and that the labels aren't obviously wrong. Log the review in `AUDIT.md`.
- [ ] **(Day 1)** Final human review before the first public deploy — the agent flags "ready," it does not push to production URLs unprompted.
- [ ] **(Day 2)** Send each teammate their lane brief (from `meta_roadmap.md` Day 2) **before** they open an agent session.
- [ ] **(Day 4)** Confirm the actual demo-day network (venue wifi vs. phone hotspot) and test latency on it, not on home broadband.
- [ ] **(Ongoing)** You are the sole integrator. Every merge to `main` and every change to a FROZEN file goes through you.

## Done

*(move confirmed items here with a date — don't delete)*
- [ ] **(Day 1)** Fix `backend/.env`: it currently holds the three `NEXT_PUBLIC_*` frontend variables (a copy of `frontend/.env.local`) instead of the four keys in `backend/.env.example`. Fill in the real `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from the Supabase dashboard (service-role key, **not** the anon key), plus `GEMINI_API_KEY` and `FRONTEND_ORIGINS`. The backend cannot reach the DB until this is done, and Block 2's insert/select verification cannot be run.
- [ ] **(Day 1)** Run `backend/schema.sql` in the Supabase SQL Editor, then run the six verification queries and the cleanup block from the Block 2 hand-off. Confirm each returns a row before Block 2 is marked done.
- [ ] **(Day 1)** Confirm the 8 seeded site names really are OIL operating areas against an OIL source. Their coordinates are OSM-verified; the operatorship claim is not (web search was down when the seed was written).
