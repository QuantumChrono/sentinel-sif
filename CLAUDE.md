# CLAUDE.md

Full project instructions live in **`AGENTS.md`** — read it first, every session. This file only holds Claude-Code-specific notes that don't belong in the shared `AGENTS.md` (which other agents/tools may also read).

## Session start
1. `AGENTS.md` in full
2. `STAGES.md` → the **"Current Position"** block (day, mode, active block or lane)
3. `PATTERNS.md` in full, once it exists (written end of Day 1) — the canonical reference implementation
4. Only the `PRD.md` sections named by the current block or lane
5. Last ~5 entries of `DECISIONS.md` and `AUDIT.md`

**Do not read `meta_roadmap.md`.** It is the human's build playbook — schedules, manual steps, and the prompts that get pasted to you. Reading it burns context on instructions you already receive directly.

## The mandate that outranks everything
`AGENTS.md` § **Boring Architecture Mandate**. Simple, explicit, boring; a beginner must understand any file's exact responsibility at a glance. Banned filenames (`utils`, `helpers`, `common`, `core`, `manager`, `service`, barrel `index.ts`), max 3 folder levels, no file over ~200 lines, no abstraction with one caller. If you catch yourself writing "this makes it more extensible," stop and simplify instead.

## Lane discipline (Days 2–4)
- Check the FROZEN file list in `STAGES.md` before editing anything. Frozen files break every lane silently when changed — integrator sign-off plus a `DECISIONS.md` entry, no "one-line fix" exception.
- Never edit a file outside the active lane's ownership list. Cross-lane need → log it in `DIY.md`, don't reach across.

## Claude-Code-specific notes
- Don't run destructive git commands (force-push, hard reset, branch deletion) without explicit confirmation in the current session.
- Don't `git push` to a remote or deploy target without confirmation — see Day 1 Block 9 and the final-human-review line in `DIY.md`.
- Run lint/typecheck before marking any block's or lane task's exit criteria met.
- Prefer editing existing files over creating new ones. "The best code is the code that doesn't exist" applies to files too — no new module for something that fits in an existing one.
- Report failures plainly. If a metric is bad, log the real number in `AUDIT.md`; if a step was skipped, say which. Never present an unrun check as passing.
- Build/test/lint commands: **fill in during Day 1 Block 1**, once `package.json` and the Python toolchain exist, so they don't need rediscovering every session.

```
frontend:  npm run dev   |  npm run build  |  npm run lint  |  npx tsc --noEmit
backend:   uvicorn main:app --reload  |  ruff check .  |  pytest
```

## File map (all governed by `AGENTS.md`)
`PRD.md` (locked spec) · `STAGES.md` (plan, current position, lane ownership, FROZEN list) · `PATTERNS.md` (reference implementation, from Day 1) · `DECISIONS.md` (why) · `AUDIT.md` (findings) · `DIY.md` (human tasks) · `meta_roadmap.md` (human playbook — not for agents)
