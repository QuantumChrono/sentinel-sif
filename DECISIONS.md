# DECISIONS.md — Decision log
Format/rules: see `AGENTS.md` § Logging protocols. Newest entries at the bottom.

---

### [Planning] Synthetic OSHA-localized data over waiting for real OIL data — 2026-08-24
Decision: build the dataset from OSHA Severe Injury Report narratives, localized via an offline LLM script to Indian oil-rig context.
Context: no access to OIL's actual HSSE report data for this hackathon.
Alternatives: hand-writing synthetic reports from scratch; other public safety-incident sources.
Rationale: OSHA data gives real severity outcomes and real narrative language patterns — more defensible under judge questioning than fully invented text. Limitation stated openly in the pitch, not hidden.

### [Planning] Cut predictive time-series forecasting — 2026-08-24
Decision: no "future incident probability" feature.
Context: appeared in an earlier external draft blueprint as an "X-factor."
Alternatives: building it on the synthetic dataset's fabricated time distribution.
Rationale: no real historical time-series exists to support a forecast; faking one risks credibility if a judge asks about baseline variance. Undermines the feasibility/practicability judging criteria.

### [Planning] NER highlighting over SHAP/LIME for explainability — 2026-08-24
Decision: spaCy NER span extraction as the explainability mechanism, not SHAP/LIME on the classifier.
Context: "explainable AI" flagged as judge-pleasing in an early draft blueprint.
Alternatives: SHAP/LIME on the fine-tuned DistilBERT classifier.
Rationale: SHAP/LIME adds meaningful inference latency, risking a sluggish live demo (NFR: <3s end-to-end). NER highlighting looks visually equivalent for a fraction of the cost.

### [Planning] Cut live WhatsApp/voice ingestion and RAG chatbot — 2026-08-24
Decision: neither built in the 5-day window.
Context: both appeared in an early draft blueprint as differentiators.
Alternatives: a minimal version of one of them.
Rationale: each is a separate project's worth of integration surface relative to time available; neither directly answers a stated problem-statement requirement. Scoped out explicitly, mentioned as a deliberate cut in the pitch.

### [Planning] Confidence-threshold Manual Review Queue kept as Tier 1 — 2026-08-24
Decision: low-confidence classifications route to a review queue instead of auto-publishing; stays in scope even under time pressure.
Context: weighing which "actionability" feature to prioritize with limited build time.
Alternatives: real-time SMS/WhatsApp alerting (moved to Tier 2/simulated only).
Rationale: cheap UI/routing feature, not a new model. Honest answer to "what happens when your model is wrong" — a near-certain judge question.

### [Planning] Sequential stage discipline replaced with day/lane discipline — 2026-08-24
Decision: `STAGES.md` restructured from 5 sequential stages into Day 1 sequential blocks plus Days 2–4 parallel lanes with an explicit file-ownership map and a FROZEN file list. `PRD.md` untouched.
Context: the operating model changed from one person over five days to one person building the full baseline on Day 1, then four teammates working concurrently on Days 2–4 with the builder acting as integrator.
Alternatives: keeping strict one-stage-at-a-time discipline (blocks the Day 1 compression and makes concurrent lanes a rule violation every session); dropping stage discipline entirely (invites the cross-file improvisation the original rule existed to prevent).
Rationale: the original rule's real purpose was preventing mismatched assumptions across boundaries, not sequencing for its own sake. With several agents running at once, the boundary that matters is *file ownership*, not *time*. FROZEN files preserve the original protection — nobody invents an API contract — while allowing genuine parallelism.

### [Planning] Cut the separate mock-endpoint pass — 2026-08-24
Decision: the frozen Pydantic contract in `backend/schemas.py` is the only contract artifact. No stage builds all 7 endpoints as mock JSON first and then rebuilds them for real.
Context: the original plan had a mock-JSON pass in one stage and its removal in a later one — sound when frontend and backend were built days apart by an agent with no shared memory of the contract.
Alternatives: keeping the mock pass (roughly doubles endpoint work and creates a dead code path that must be found and deleted later).
Rationale: on Day 1 one person owns both sides within hours. A typed schema file gives the frontend a real contract to build against at zero duplication cost, and typed responses fail loudly at the boundary where mock JSON drifts silently.

### [Planning] Interim inference implementations behind frozen signatures — 2026-08-24
Decision: Day 1 Block 5 ships deliberate interim implementations behind the three final inference signatures (`classify_sif`, `tag_iogp_rules`, `extract_precursors`) so the full app is built and demoable before fine-tuned weights exist. Block 8 swaps in real weights and **deletes** the interim code.
Context: DistilBERT fine-tuning is wall-clock-bound (dataset generation plus two training runs) and cannot be compressed by working faster. Blocking the frontend on it would leave most of Day 1 idle.
Alternatives: waiting for real weights before building any UI (serializes the day, likely misses the baseline target); shipping the interim version as a permanent fallback (dishonest under demo, and a hidden second code path).
Rationale: it decouples wall-clock-bound training from hands-on UI work, which is what makes a one-day baseline arithmetically possible. The risk — interim code surviving into the demo — is controlled by making deletion an explicit Block 8 exit criterion verified with grep, not a good intention. Under no circumstances is the interim path reachable at demo time.
