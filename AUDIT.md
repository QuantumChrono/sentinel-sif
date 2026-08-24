# AUDIT.md — Findings log
Format/rules: see `AGENTS.md` § Logging protocols. Real numbers only, log negative results too, newest at bottom.

---

### [Planning] Governance docs referenced a stage plan that no longer exists — 2026-08-24
Type: inconsistency | Severity: med
Finding: `AGENTS.md` and `CLAUDE.md` both pointed at stage numbers from a superseded ~16-stage plan while `STAGES.md` defined only Stages 0–4. Concrete dangling references: "Stage 10 explicitly requires removing Stage 5's mock endpoints" and "frontend/UI stages (11-14)" in `AGENTS.md`; "see Stage 16" in `CLAUDE.md`. An agent bootstrapping from these files would have looked for stages that do not exist, and the skill-routing hint ("stages 11-14") would never have matched any real stage. Status: resolved — both files rewritten against the day/lane model; all stage-number references replaced with day/block/lane references.

### [Planning] `meta_roadmap.md` is unreadable by agents by design — 2026-08-24
Type: tech-debt | Severity: low
Finding: `meta_roadmap.md` contains the human playbook, including copy-pasteable prompts intended *for* the agent. An agent that reads it would consume a large amount of context re-reading instructions it already receives directly, and could mistake a Day-3 prompt for a current instruction. Status: accepted — mitigated by an explicit "do not read `meta_roadmap.md`" line in `CLAUDE.md`. Accepted rather than resolved because nothing mechanically prevents a session from opening the file.
