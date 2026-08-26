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

### [Day 1 / Block 1] Next.js pinned to 15.5.23, not the create-next-app default — 2026-08-24
Decision: `create-next-app@15.5.4` scaffolded `next@15.5.4`; immediately pinned up to `next@15.5.23` (and `eslint-config-next` to match). All frontend and backend dependencies pinned to exact versions, no carets.
Context: `npm audit` on the fresh scaffold reported 1 critical + 2 high advisories, the critical being RCE in the React flight protocol (GHSA-9qr9-h5gf-34mp).
Alternatives: staying on 15.5.4 (ships a known critical RCE); jumping to `next@16.3.2`, which is what `npm audit fix --force` wants (major-version change to a stack `PRD.md` fixes as "Next.js App Router", on day 1 of a 5-day build).
Rationale: 15.5.23 is the patched release inside the same minor, so it clears the critical without substituting the stack. Exact pins are required by `AGENTS.md` § Coding standards and keep every teammate's Days 2–4 install identical.

### [Day 1 / Block 1] Frontend `public/` directory deleted outright — 2026-08-24
Decision: removed all five create-next-app SVGs plus `app/favicon.ico`, then removed the now-empty `public/` directory rather than leaving it as an empty placeholder.
Context: Block 1 requires deleting every piece of demo content; nothing in the current design serves a static asset.
Alternatives: keeping an empty `public/` "since we'll need it eventually".
Rationale: an empty directory is speculative scaffolding, which `AGENTS.md` bans. Next.js recreates the convention the moment a real asset exists; a favicon or logo can add it back in one line when there is an actual file to put there.

### [Day 1 / Block 2] `on delete cascade` on the three report-child foreign keys — 2026-08-24
Decision: `classifications.report_id`, `iogp_tags.report_id`, and `precursors.report_id` are declared `references reports (id) on delete cascade`. The other two FKs — `reports.site_id`, `users.site_id`, `classifications.reviewed_by` — get plain `references` with no cascade.
Context: `PRD.md` § Database schema specifies the columns and marks them `fk` but says nothing about delete behaviour, so a choice had to be made rather than defaulted silently.
Alternatives: plain `references` everywhere (deleting a report then fails on its own children, or leaves orphan classifications that every analytics query has to defend against); `on delete cascade` everywhere (deleting one user would delete the classifications they reviewed, destroying real review history).
Rationale: a classification, tag set, or precursor span has no meaning without its report — it is child data, so it follows the parent. A site or a reviewing user is a separate entity that reports merely point at; deleting one must never silently delete safety records. No column was added, renamed, or retyped, so this needs no `PRD.md` deviation.

### [Day 1 / Block 2] `supabase==2.31.0` added to backend requirements — 2026-08-24
Decision: added the one dependency `supabase==2.31.0` (exact pin, latest on PyPI as of 2026-08-24), pulling `postgrest`, `supabase-auth`, `storage3`, `realtime`, `supabase-functions` at the same version.
Context: `PRD.md` § Tech stack fixes Supabase as DB/Auth; `backend/database.py` needs the official client.
Alternatives: raw `psycopg` against the Postgres connection string (loses Supabase Auth integration that Block 7 needs, and means hand-writing SQL in every route); an ORM such as SQLAlchemy (`AGENTS.md` bans speculative abstraction, and the block brief explicitly rules out an ORM).
Rationale: it is the client the platform we already committed to ships, and it keeps Block 7's auth work on the same library instead of bolting a second DB path on later.

### [Day 1 / Block 3] Gemini reached through the OpenAI-compatible endpoint, no new dependency — 2026-08-25
Decision: `scripts/localize_dataset.py` calls Gemini via the already-installed `openai==2.20.0` client pointed at `https://generativelanguage.googleapis.com/v1beta/openai/`, default model `gemini-flash-latest`.
Context: the human picked Gemini for the offline localization key (`DIY.md`, Day 0) and named `gemini-flash-latest`. `openai`, `pandas`, `python-dotenv` and `tqdm` are already present in the environment.
Alternatives: adding `google-genai` as a dependency (a new pin, a second SDK idiom in the repo, for one offline script); raw `requests` against the REST API (hand-rolling retry, JSON-mode and usage parsing that the SDK already does).
Rationale: `AGENTS.md` requires a rationale for any new dependency and prefers not adding one at all. Google ships an OpenAI-compatible surface specifically for this, so zero new pins buys the same call. If the endpoint ever misbehaves, swapping in `google-genai` touches one `client = ...` line.

### [Day 1 / Block 3] The LLM never sees or decides `sif_potential` — 2026-08-25
Decision: the prompt contains no label, no mention of SIF, and no severity language. Python assigns `sif_potential` from `EventTitle`/`NatureTitle` before any call is made; the record carries the label plus a `sif_rule_hits` field (`A1`/`A2`/`A3`/`B`) naming which test fired.
Context: `STAGES.md` Block 3 forbids letting the generating LLM grade its own labels, and `LABELING_RULE.md` § 2 derives labels only from OSHA's structured coding so they survive the rewrite.
Alternatives: asking the model to also classify (a self-graded label, and the exact thing a judge would attack); passing the label as context to "help" the rewrite (invites the model to dramatise positives and soften negatives, which would leak the label into prose style and let the classifier learn the tell instead of the hazard).
Rationale: the two jobs are kept mechanically separate, not just conventionally. `sif_rule_hits` means every row in the dataset can be traced to the clause that labelled it without re-running anything.

### [Day 1 / Block 3] Noise tiers are a shuffled fixed list, not a per-row dice roll — 2026-08-25
Decision: `assign_noise_tiers` builds exactly `round(n*0.10)` heavy, `round(n*0.30)` moderate, remainder clean, then shuffles with a seeded RNG. For 1,000 rows that is exactly 100/300/600, asserted in `--verify-rule`.
Context: `PRD.md` states ~60% clean / 30% moderate / 10% heavy and calls it "not uniform".
Alternatives: `random.choices` with weights per row — the obvious approach, but at n=20 it plausibly yields 4 heavy or 0 heavy, and the review sample is the one place the distribution is checked by eye.
Rationale: the tier is later used to measure accuracy per noise level, so the denominator should be exact rather than approximately right. Seeded so a resumed run reassigns the same tier to the same OSHA ID.

### [Day 1 / Block 3] Python computes precursor spans; the LLM only quotes — 2026-08-25
Decision: the model returns each precursor as a verbatim substring of its own `localized_text`; `find_span` locates it with `str.find` and emits `{text, start, end}`. A quote that is not found is dropped to `null` rather than stored with a guessed offset. `--verify-rule` asserts the span slices back to its own text.
Context: `PRD.md` § Labeling schema needs `precursor_*` as text spans, and Block 7's "Magic View" highlights `raw_text[start:end]`. `STAGES.md` Block 7 forbids hand-writing a span offset.
Alternatives: asking the model for integer offsets directly (LLMs cannot count characters reliably — off-by-a-few offsets would silently mis-highlight the hero screen); fuzzy-matching a paraphrase back onto the text (invents a span the narrative does not contain).
Rationale: a wrong offset is worse than a missing one — a missing precursor shows nothing, a wrong one highlights the wrong words in the demo's explainability screen. One case-insensitive retry is allowed; anything beyond that returns `null`.

### [Day 1 / Block 3] Review sample is 50/50 by class, and is not the full-run sampling strategy — 2026-08-25
Decision: `--sample 20` draws 10 positives and 10 negatives, seeded. The full `--count` run uses the same function, so its balance is also 50/50 unless changed.
Context: `LABELING_RULE.md` § 7 is explicit that 66.3% is a frame statistic and that the training balance is a separate decision, deliberately deferred (§ 10). The human must review both classes to judge whether labels look wrong.
Alternatives: sampling at the frame's natural 66.3% (a 20-row review would show ~13 positives and ~7 negatives — fewer negatives to inspect, and a reviewer sees less of the boundary).
Rationale: for a 20-row eyeball review, equal classes maximise what the reviewer can catch. The 2,000–3,000-row balance is still an open decision and gets its own entry before the full run — this entry does not settle it.

### [Day 1 / Block 3] Out-of-canon IOGP rules are dropped, never renamed onto the canonical 9 — 2026-08-25
Decision: any `iogp_rules` value the model returns that is not an exact string match to `PRD.md`'s canonical 9 is discarded and recorded separately in `iogp_rules_rejected`.
Context: `PRD.md` § Glossary states the 9 rules must not be renamed or merged.
Alternatives: fuzzy-mapping near-misses ("Working at Heights", "Line of Fire Awareness") onto the canonical name — silently invents a mapping rule nobody wrote and would let a tenth category in through a spelling variant.
Rationale: keeping the rejects in the record makes prompt drift visible during the review instead of hiding it behind a normalizer. If a variant recurs often, the prompt gets fixed, not the data.

### [Day 1 / Block 3] Model pinned to `gemini-3.7-flash`; client gets an explicit timeout and no SDK-level retries — 2026-08-25
Decision: `--model` defaults to `gemini-3.7-flash` (the human's specified id, verified to resolve by a real call). The client is constructed `timeout=60.0, max_retries=0`.
Context: the previous default `gemini-flash-latest` was unverified and is not a valid id. Separately, measured call latency on this endpoint ranges 10-31s with occasional indefinite stalls and transient 503s.
Alternatives: the SDK's 600s default timeout (a stall becomes an apparent hang, which is what the first Ctrl+C actually was); leaving `max_retries` at the SDK default of 2 (then the script's visible 5-attempt loop is really up to 15 requests, which on a 20-request daily quota is fatal and invisible).
Rationale: one retry authority, in the script, where the log line shows it. 60s is above the slowest observed success (31s) and well below a hang.

### [Day 1 / Block 3] A per-day quota error is not retried — 2026-08-25
Decision: `localize_row` re-raises immediately when the error text contains `PerDay`, skipping the backoff loop.
Context: the free tier caps `gemini-3.7-flash` at 20 requests per day per project. The generic 5-attempt backoff treated that as transient and spent 4 extra requests per row against an already-exhausted budget.
Alternatives: sleeping on the server's `retryDelay` (7-59s in the observed bodies — those values are the *per-minute* hint and do not clear a daily cap, so the run would sleep and still fail); dropping the retry loop entirely (loses genuine per-minute and 503 recovery, which is the case it was built for).
Rationale: the `.jsonl` checkpoint already makes a daily cap survivable — the row resumes tomorrow. Burning requests to confirm a quota that cannot clear within the run is strictly worse than failing the row now.

### [Day 1 / Block 3] `scripts/requirements.txt` kept separate from `backend/requirements.txt` — 2026-08-25
Decision: added `scripts/requirements.txt` pinning the three packages this script actually imports (`pandas==2.2.3`, `openai==2.20.0`, `python-dotenv==1.2.1`). The script was run against the global Python 3.11.9 interpreter, which already has all three; `backend/.venv` was left untouched.
Context: `backend/.venv` exists and holds only the five `backend/requirements.txt` pins — it has `python-dotenv` but no `pandas` and no `openai`. Something had to give: either the venv gains two heavy packages or the script runs elsewhere.
Alternatives: installing `pandas` + `openai` into `backend/.venv` (the deployed backend must not carry an LLM client or pandas — Block 9 deploys that env to HF Spaces, and `AGENTS.md` forbids dependencies without a rationale; this script is offline-only and never imported by `backend/`); a third venv just for `scripts/` (more environment management than a once-per-project script justifies).
Rationale: the dependency set is now recorded and reproducible either way, and the deployed backend's environment stays clean. Flagged for the human in `DIY.md` since "which interpreter runs the scripts" is an environment convention worth confirming, not silently establishing.

### [Day 1 / Block 3] LLM provider switched Gemini -> Groq; model pinned to `openai/gpt-oss-120b` - 2026-08-25
Decision: `localize_dataset.py` now calls Groq's OpenAI-compatible endpoint (`https://api.groq.com/openai/v1`) with `GROQ_API_KEY`. `--model` defaults to `openai/gpt-oss-120b`. Every Gemini code path is deleted, not disabled.
Context: the Gemini free-tier daily quota (20 requests/day/model) was exhausted with 3 of 20 sample rows written. The human supplied a Groq key and specified `llama-3.3-70b-versatile`.
Alternatives: `llama-3.3-70b-versatile` as specified - preflight proved it returns HTTP 404 `model_not_found` on this key, and `models.list()` shows no Llama chat model on the account at all (only Meta Prompt-Guard classifiers); `qwen/qwen3.6-27b` and `openai/gpt-oss-20b` (smaller, weaker at holding a strict multi-report JSON contract); waiting for the Gemini quota to roll over (blocks Block 3 for a day).
Rationale: `openai/gpt-oss-120b` is the largest general-purpose chat model the account can actually reach, and a live call verified it holds the batch contract and produces per-report noise tiers correctly. The human chose it over the alternatives after the 404 was reported.

### [Day 1 / Block 3] Narratives are batched 5 per request, with an index-alignment guard - 2026-08-25
Decision: `localize_row` became `localize_batch`; `BATCH_SIZE = 5`. Each report carries its own site, noise tier and mechanics in the prompt, and each returned result must self-report the `index` it rewrites. A response of the wrong length, or one whose result at position *i* does not claim `index == i+1`, raises and the whole batch is retried. Parsing and validation sit *inside* the retry loop.
Context: the human asked for conservative batching of 5, one result per input, in order, with failed batches retried whole.
Alternatives: trusting positional order alone (a model that silently drops report 2 would shift every later narrative onto the wrong OSHA row's `sif_potential` - dataset corruption no downstream check would catch); accepting a short batch and backfilling the missing rows (same misalignment risk, plus partial writes).
Rationale: a misaligned batch is worse than a failed one. This guard fired for real: two batches in the first run returned 2 and 3 results for 5 inputs, and were rejected rather than written.

### [Day 1 / Block 3] Retry honours the server's stated wait instead of exponential backoff - 2026-08-25
Decision: `retry_delay` parses `"try again in <N>s"` out of the Groq 429 body and sleeps `N + 1`, falling back to `2 ** attempt + jitter` only when no hint is present. `--workers` defaults to `1`.
Context: Groq's free tier caps this model at 8,000 tokens per minute. One 5-narrative batch costs ~4,000 tokens.
Alternatives: keeping `2 ** attempt` (1/2/4/8s - every attempt lands inside the same exhausted 60s window and is spent without ever waiting long enough; this is exactly how the first Groq run lost 15 of 20 rows); `workers=2` (fires 8,000 tokens instantly and manufactures the 429 it then has to wait out).
Rationale: the rate limiter clears on wall-clock time and the server states the number - guessing a shorter one cannot succeed. Serial batches at ~4,000 tokens each fit the window without contending.

### [Day 1 / Block 3] The 3 Gemini rows were regenerated by Groq, including their `iogp_rules` - 2026-08-25
Decision: `data/sample/localized.jsonl` was backed up and cleared so all 20 rows come from one model. The 3 rows keep their deterministic fields byte-identical (asserted against the backup: `site_name`, `region`, `noise_tier`, `sif_potential`, `sif_rule_hits`, `osha_*`); their `raw_text`, precursor spans and `iogp_rules` are Groq's.
Context: the human asked for both "deterministic IOGP labels unchanged" and "all 20 rows generated by the same model so the sample is internally consistent". `iogp_rules` is **not** deterministic - it is LLM-assigned (`LABELING_RULE.md` s10 leaves IOGP assignment explicitly out of scope, and no written rule derives it), so the two instructions conflicted on those 3 rows.
Alternatives: carrying the Gemini `iogp_rules` over onto Groq-generated prose (mixes two models' judgment on the one field the human wanted consistent, and pins IOGP tags to a narrative they were not read from); writing a deterministic IOGP mapper (a new labeling rule nobody has specified - out of scope for this block).
Rationale: the conflict was surfaced to the human rather than silently resolved, and they chose consistency. Only `sif_potential` was ever deterministic, and it is unchanged and re-verified against the raw CSV.

### [Day 1 / Block 3] Localization prompt tightened over four versions; v4 vs v5 tradeoff left to the human - 2026-08-25
Decision: the prompt was rewritten four times against the v1 review findings, and each version regenerated all 20 rows so the sample is never a mix of prompt versions. v5 is what sits in `data/sample/localized.jsonl`. v2-v4 are kept as backups outside the repo (`%TEMP%/localized_groq_v{1,2,3,4}_backup.jsonl`) because v4 beats v5 on two measured axes and the choice between them is the human's.
Context: the v1 review found surviving US context (5 of 20 rows), Hinglish parroted verbatim from the prompt's own examples, and ~7 of 20 barrier spans naming the outcome instead of a failed control.
Alternatives: accepting v1 with a note (the localization failure rate was ~20% and the Hinglish was fake); one big prompt rewrite (each fix was verified in isolation instead, which is what exposed the over-correction in v2).
Rationale: measured per version rather than argued. v1 barrier 19/20 but 5 US artifacts and 1/8 noisy rows code-switching; v2 fixed US context and Hinglish but collapsed barrier spans to 1/20; v3 recovered to 14/20; v4 reached 0 US artifacts, 14/20 barriers, 72/80 spans, 10/20 IOGP; v5 fixed v4's one fabricated barrier and its stock-phrase Hinglish but dropped barrier spans to 5/20 and IOGP to 6/20. The two remaining defects trade against each other, so the human picks.

### [Day 1 / Block 3] Typographic punctuation is folded to ASCII in Python, not asked for in the prompt - 2026-08-25
Decision: `to_ascii_punctuation` maps the U+2010-U+2015 dashes, curly quotes, prime marks, ellipsis and exotic spaces onto ASCII. It runs on `localized_text` and on every precursor quote before `find_span`, so stored offsets always come from the normalized text. Asserted in `--verify-rule` (now 25 checks).
Context: v3 still returned U+2011 and U+2013 in 2 of 20 rows despite the prompt explicitly asking for plain ASCII punctuation.
Alternatives: repeating the instruction more forcefully (character-level compliance is not something an LLM is reliable at, and two rows had already slipped through); normalizing at training time in `backend/` (the spans are computed here, so a later fold would invalidate every stored offset).
Rationale: this is exactly the "Python validation/extraction" stage of the documented architecture. A deterministic two-line table beats a prompt instruction that measurably does not hold, and doing it before span computation keeps `raw_text[start:end]` honest.

### [Day 1 / Block 3] `max_completion_tokens` pinned because gpt-oss-120b is a reasoning model - 2026-08-25
Decision: `localize_batch` passes `max_completion_tokens=4000`. `reasoning_effort` is left at its default.
Context: a batch failed twice with HTTP 400 `json_validate_failed` / "max completion tokens reached before generating a valid document", and other attempts returned 2 or 3 results for 5 inputs. A measured trivial call spent 91 of its 144 completion tokens on hidden reasoning, so the longer prompt plus 5 reports overran the endpoint default and truncated the JSON mid-document.
Alternatives: `reasoning_effort="low"` (measured to cut completion tokens from 144 to 85, but the reasoning is what strips US context and distinguishes a barrier from an outcome - the two things this regeneration existed to fix); smaller batches (the human specified 5, and the truncation is a token ceiling, not a batch-size limit).
Rationale: raise the ceiling, keep the reasoning. The truncation was a budget problem, not a capability problem.

### [Day 1 / Block 3] Localization split into two LLM stages - 2026-08-25
Decision: `localize_batch` now makes two requests per batch. Stage 1 (`PROMPT_REWRITE`) rewrites prose only and is never shown the words "IOGP" or "precursor". Stage 2 (`PROMPT_EXTRACT`) receives only the finished Indian narrative plus the coded hazard/injury titles - never the OSHA original - and returns `iogp_rules` and the four precursor quotes. Python normalizes punctuation between the stages and computes every offset after, so `raw_text[start:end]` round-trips. The shared request/retry/index-alignment code is factored into `call_llm_batch`, which now has two callers.
Context: over four versions of the combined single-call prompt, barrier-span coverage swung 19/20 -> 1/20 -> 14/20 -> 14/20 -> 5/20 and IOGP coverage decayed 16/20 -> 6/20 on rewrite-instruction wording alone. The judgment fields were hostage to prose rules.
Alternatives: a fifth combined-prompt revision (four attempts had already shown the instability is structural, not a wording problem); extracting spans in Python with rules (a barrier failure is a semantic judgment, not a pattern - and `LABELING_RULE.md` s10 deliberately leaves IOGP out of scope).
Rationale: a stage that only extracts cannot be crowded out by rewrite rules. Measured: IOGP recovered from 6/20 to 13/20 tagged, both heavy rows became genuinely messy for the first time, and Stage 2 stopped quoting outcome words entirely. Stage 2 not seeing the US original also removes the route by which US wording re-entered a span it must quote verbatim.

### [Day 1 / Block 3] Stage 2 is shown the coded titles but not the OSHA narrative - 2026-08-25
Decision: `EXTRACT_ITEM` carries `EventTitle`, `NatureTitle` and the rewritten text. It does not carry `Final Narrative`.
Context: Stage 2 must quote spans character-for-character out of the stored `raw_text`, and must map IOGP from the incident mechanism.
Alternatives: also passing the OSHA narrative (it would let US wording leak back into a quoted span, and gives the model two conflicting texts to quote from); passing neither title (the coded hazard/injury pair is what distinguishes an ordinary fall from a fall-from-height, which is exactly the IOGP judgment).
Rationale: the titles are coded metadata, not prose, so they inform the mapping without supplying quotable text.

### [Day 1 / Block 3] Barrier spans sourced by entailment only, never fabricated - 2026-08-25
Decision: `precursor_barrier_failure` may be returned only where the narrative's own stated mechanics entail that a specific control was absent or defeated - a motor starting while someone works inside the machine entails isolation was not applied. Everywhere else it is null. Expected coverage ~8-10 of 20, against an original target of 17/20, and the prompt is explicitly not to be tuned to raise it.
Context: the 20-row two-stage audit returned 1/20 barrier spans. A word-boundary scan of all 20 source narratives found ZERO naming a failed control: OSHA severe-injury reports record what happened, not which control was missing. An earlier "5/20 sources name a control" figure was a substring bug in the diagnostic - `ppe` matching inside `slipped` and `tripped`. Every earlier prompt version that scored 14-19/20 reached it by inventing a control and then quoting its own invention.
Alternatives: accept sparse nulls and train the NER head on 3 span types (drops a PRD span type and weakens the Magic View); source barriers from a corpus that records them (a new download and mapping, impossible inside the remaining session); accept fabrication (highest coverage, and it teaches a safety model to hallucinate causes - the worst outcome available here).
Rationale: entailment is inference from stated fact rather than invention, so every span is defensible against the narrative it came from. The honest ceiling of this corpus is ~8-10, and the limitation is logged in `AUDIT.md` with its cause rather than hidden behind a better-looking number. A judge asking "how do you know a barrier failed?" gets a quotable clause instead of a shrug.

### [Day 1 / Block 3] Unit and object-class conversion stopped in the rewrite prompt - 2026-08-25
Decision: stage 1 reproduces every source quantity verbatim with its original unit, and may not change an object into a different class of object.
Context: the audit caught 800 lb -> 200 kg, 200 lb -> 200 kg (200 lb is ~91 kg), a 1000 lb dolly capacity -> 1000 kg, and a drum rewritten as a gas cylinder. A correct 2 inch -> 5 cm elsewhere shows this is unreliability, not incapacity.
Alternatives: instructing it to convert more carefully (four prompt versions established that character- and arithmetic-level compliance is not something this model holds reliably); converting in Python afterwards (needs a unit parser over free prose, far more machinery than leaving the number alone).
Rationale: quantities and object classes carry the incident mechanics, and `sif_potential` is derived from the mechanics, so a wrong conversion is a corrupted training row rather than a cosmetic blemish. A gas cylinder is a pressure vessel - a different hazard class from a drum. Not converting is both cheaper and strictly more faithful; mixed units in an Indian report are realistic anyway.

### [Day 1] Day 1 delivers a localhost prototype; training, weight swap, and deploy are Day 2 - 2026-08-25
Decision: Day 1 ships the application with keyword inference behind the three frozen signatures, verified on localhost. Training and the weight swap become Lane A's Day 2 priorities 1 and 2; the deploy becomes the integrator's Day 2 morning. The interim token is `INTERIM_LANE_A` from birth so it names its owner rather than a block number. The Day 1 exit gate checks only what is verifiable on localhost tonight, and the baseline tag is `v0.1-baseline-interim`.
Context: two hours of hands-on time remained against an original Day 1 of 11-13 hours. Generating 1,200 rows costs ~1.9M tokens at Groq's ~8,000 tokens/minute, so the dataset occupies ~4 hours of wall clock and finishes after the session ends. Everything downstream of it - both fine-tunes, the threshold tune, the latency measurement - was therefore unreachable today. Four teammates need something to fork from in the morning.
Alternatives: keeping training and cutting the frontend instead (Lane B and Lane C are both blocked without a page of their type to copy, so it trades one blocked lane for two); shrinking the dataset enough to train today (~600 rows leaves several of the 9 IOGP rules with almost no examples, making per-rule F1 meaningless); keeping the deploy and cutting `PATTERNS.md` (that file is the one thing four parallel agents cannot work without).
Rationale: the block boundary that makes this cheap already existed - Block 5's frozen signatures mean the swap is a contained change behind a fixed interface, which is the property they were chosen for. What keeps the deferral honest rather than a hidden shortcut is that it is grep-able (`INTERIM_LANE_A`), owned (Lane A, named in `STAGES.md` and in their brief), and stated in `PATTERNS.md` under "What is deliberately unfinished". The gate was rewritten for the same reason: a checklist asking about deployed URLs that do not exist teaches you to wave the checklist through.

### [Day 1 / Block 4] PRD stage order kept; spellchecker given a protected vocabulary instead - 2026-08-25
Decision: the PRD order (acronym expansion -> spellcheck -> Hinglish normalization) is implemented exactly as written, and the spellchecker is handed a protected vocabulary it must never touch: every acronym key and expansion, 102 oilfield/Indian domain words, and every Roman-Hindi key in the lexicon.
Context: run naively that order cannot work. pyspellchecker does not know `nahi`, `bina` or `chahiye`, so stage 2 rewrites them into English lookalikes and stage 3 finds nothing left to normalize. The same holds for bare acronyms - an unexpanded `ppe` becomes "pope", which is why acronyms must still expand first.
Alternatives: reordering to Hinglish -> acronyms -> spellcheck (works, but silently contradicts a locked PRD contract and is the wider change); skipping spellcheck on any line containing Hindi (loses typo correction on exactly the messiest 40% of the corpus, which is where it is worth most).
Rationale: a protected word list is narrower than a reordering, keeps the documented contract intact, and is auditable as data rather than as control flow. Verified both directions: `drawworks`, `khalasi`, `toolpusher`, `Duliajan`, `monkeyboard` survive stage 2, while `equipmnt` is still corrected to `equipment`.

### [Day 1 / Block 4] Hindi third-person pronouns normalize to they/them, not he/him - 2026-08-25
Decision: `usne`, `usko`, `uska`, `uski`, `uske` and `usse` all map to they/them/their. A self-check asserts no lexicon entry maps to a gendered English word.
Context: the first implementation mapped `usne` -> "he". Sample 2021032603 describes a female worker and came out as "she slipped on dry leaves ... he said" about one person - the pipeline invented a gender the report never stated.
Alternatives: mapping to "he" as a generic (invents a fact, and the field workforce is not uniformly male); mapping to "he/she" (noisy for a tokenizer and still enumerates); dropping the pronouns entirely (loses the subject of the clause the NER reads).
Rationale: Hindi third-person pronouns carry no gender, so they/them is the accurate translation rather than a stylistic preference. The mistake also has real downstream cost: `cleaned_text` is what the classifier reads and what a human sees in the Report Detail view, so an invented gender becomes a false statement about a real incident.

### [Day 1 / Block 4] Colliding Hindi words stay untranslated, and the gate is automated - 2026-08-25
Decision: any Roman-Hindi word whose spelling is also a common English word is NOT mapped. 58 such words are listed and excluded. A self-check asks a fresh English dictionary whether any lexicon key is an English word and fails unless that key sits in a reviewed 11-word allowlist.
Context: four collisions shipped and were caught by reading the 10-sample output, not by the passing 43/43 test - `sir` (honorific), `pair` (of gloves), `log` (book), `mat` (rig mat). The only assertion in place checked that HINGLISH and COLLIDES_WITH_ENGLISH are disjoint, which passes happily while a collision sits in HINGLISH alone.
Alternatives: mapping them and accepting the damage (rewrites the 60% of the corpus that is plain English - the expensive failure); context-sensitive disambiguation (a language model at inference time, which `PRD.md` forbids on the runtime path).
Rationale: losing a few Hindi words degrades one report slightly; rewriting English text corrupts the majority of the corpus. The measured cost is recorded rather than hidden - `to`, `se`, `aur`, `par`, `ki`, `ko` and `ne` remain in the cleaned text, so the output is translationese and is logged in `AUDIT.md` as a known limitation. The automated gate matters more than the fix: it converts "I remembered to check" into "the suite fails if I forget".

### [Day 1 / Block 4] 11 acronyms recorded as UNVERIFIED and deliberately not expanded - 2026-08-25
Decision: `dsv`, `wd`, `temp`, `oim`, `mop`, `tt`, `sh`, `lt`, `ht`, `cp` and `pm` are listed with their competing readings and are NOT expanded. A self-check asserts no acronym is both applied and unverified.
Context: `STAGES.md` Block 4 forbids guessing at an OIL acronym without marking it unverified. Each of these has more than one plausible expansion in a drilling context - `ht` is high tension or height, `pm` is preventive maintenance or afternoon, `dsv` is a drilling supervisor onshore but a diving support vessel offshore.
Alternatives: expanding the most likely reading (a coin flip that becomes the text the classifier and NER read, so a wrong guess silently rewrites the incident); dropping them from the file (loses the record of what still needs an SME).
Rationale: an acronym left alone costs one unexpanded token; an acronym expanded wrongly rewrites the mechanics of the incident. Keeping them listed with their ambiguity makes the gap resolvable by an operations SME later instead of invisible.

### [Day 1 / Block 5] Density ranks on the Wilson lower bound, and shows the raw rate - 2026-08-25
Decision: `/api/v1/analytics/density` returns a RATE (SIF-potential reports over total reports for the group) and orders rows by the Wilson score interval's 95% lower bound. Both numbers ship: `sif_rate` is the honest fraction the table displays, `rank_score` is what the ordering uses. No group is ever excluded for being small.
Context: a raw count ranks sites by how much paperwork they file, so the best reporting culture tops the table - the opposite of the intended message. But a raw rate makes 1-of-1 a perfect 100% and puts it above 24-of-40 at 60%.
Alternatives: a minimum-reports threshold ("ignore groups under 10") - hides a genuinely dangerous new site until it has filed enough paperwork, which is the wrong failure for a safety tool; Bayesian shrinkage toward the global mean (defensible, but needs a prior nobody can justify on a 20-row sample, and the number it reports is no longer the site's own rate); ordering on the raw rate and letting the UI caveat it (pushes a known-wrong ranking onto the screen the problem statement names as the expected outcome).
Rationale: Wilson asks "what is the lowest rate consistent with this evidence", which is exactly the small-denominator question - 1-of-1 scores 0.21, 24-of-40 scores 0.45, so the forty-report site correctly wins while a small site with a genuinely bad rate still climbs as evidence accumulates. It is ~10 lines of arithmetic on two integers: no dependency, no prior, no tuning. Showing both columns means "why is 100% below 60%?" is answered by the table itself rather than by a hand-wave.

### [Day 1 / Block 5] Inference reuses the labeling rule's step-0 normalization; the NER never does - 2026-08-25
Decision: `sif_classifier.py` normalizes text (lowercase, punctuation to spaces, collapse runs) before matching, exactly as `data/LABELING_RULE.md` § 5 step 0 mandates. `precursor_ner.py` deliberately does NOT, and matches the caller's exact string.
Context: the interim classifier missed a real SIF row because the narrative said `jack-knifed` while the keyword list said `jack knifed`. That is the same silent bug § 9.10 of the labeling rule records costing 1,775 mislabelled rows.
Alternatives: enumerating spelling variants per keyword (unbounded, and the next variant fails silently again); normalizing in every module for consistency (would break every precursor span, since offsets must index the string the caller passed in).
Rationale: the classifier returns no offsets, so normalizing is free there and makes the interim agree with the rule that labels its training data. The NER's entire contract is `text[start:end] == entity_text`, so the same transformation that helps the classifier would corrupt the highlighting. The asymmetry is stated in both modules' docstrings because it is the kind of "consistency" fix a later reader would otherwise apply for tidiness.

### [Day 1 / Block 5] `postgrest.APIError` imported directly to separate client errors from 500s - 2026-08-25
Decision: `routes/reports.py` and `routes/review.py` import `from postgrest.exceptions import APIError` and translate Postgres `23503` (foreign_key_violation) into a 422. `postgrest==2.31.0` ships with `supabase==2.31.0`; it is not a new install and adds nothing to `requirements.txt`.
Context: a submission naming a `site_id` that does not exist, or a review naming an unknown `reviewed_by`, is the client's error. Left alone it surfaces as a raw 500 - which `PRD.md` § Edge cases forbids during a live demo.
Alternatives: catching bare `Exception` and reading `getattr(error, 'code', None)` (drops the import, but also swallows genuine faults into a 422 and hides the shape of what was caught); pre-checking that the site exists before inserting (an extra round trip per submission, and still racy).
Rationale: the explicit exception type is the narrowest catch that does the job, and it fails loudly at import if the dependency ever moves rather than silently degrading to a bare-except. Only `23503` is translated; every other `APIError` re-raises untouched, so a real fault stays a real fault.

### [Day 1 / Block 7] `GET /api/v1/sites` added, plus two lines in FROZEN `backend/main.py` - 2026-08-26
Decision: new `backend/routes/sites.py` returning `list[SiteOut]`, registered with an import line and an `include_router` line in `main.py`. **`main.py` is FROZEN, so this needs the integrator's sign-off retroactively** - logged in `DIY.md`. No change to `schemas.py`: the endpoint returns the frozen `SiteOut` already embedded in every report response, so no contract was added, only a way to read one that existed.
Context: `PRD.md` § Frontend pages item 2 requires a site selector, and `PRD.md` § Backend API lists no way to read `sites`. Without this the Intake page has no data source for the selector at all.
Alternatives: read `sites` from the browser's Supabase client (a second data path with no server validation in front of it, breaks the single-HTTP-layer rule, and does not work today - the anon role has no grants, `42501 permission denied`, `AUDIT.md` 2026-08-25); hard-code the eight seeded sites in the frontend (mocks a table that already exists, which the Block 7 brief forbids).
Rationale: it is the smallest possible addition - 30 lines, one select, no new contract - and it keeps every backend read behind FastAPI where the service-role key lives.

### [Day 1 / Block 7] The role claim is read from `app_metadata`, never `user_metadata` - 2026-08-26
Decision: `lib/user_role.ts` reads `app_metadata.role`. An absent, empty, non-string or unrecognised claim resolves to null and lands on `/intake`. `admin` - a role in `schema.sql` that `PRD.md` gives no redirect for - lands on `/dashboard`.
Context: the redirect decides which screen a role opens, so whichever field carries the claim is the privilege boundary.
Alternatives: `user_metadata` (the field most Supabase examples use); a `role` column read from the `users` table on every page load (an extra round trip per navigation, and the table is empty today).
Rationale: `user_metadata` is writable by the user themselves through `supabase.auth.updateUser({ data: ... })`, so a role kept there lets any site supervisor promote themselves to `hse_manager` from the browser console. `app_metadata` is writable only with the service-role key, which never leaves the backend. The unknown-role default goes to the *lesser*-privileged screen so a missing claim cannot open the management view; `lib/role_check.ts` asserts that direction explicitly, including the `user_metadata` forgery path.

### [Day 1 / Block 7] Auth enforced in `middleware.ts`, not in a client-side guard - 2026-08-26
Decision: `middleware.ts` calls `supabase.auth.getUser()` and redirects before any protected page renders. The two pure role rules live in `lib/user_role.ts`, separate from `lib/supabase_client.ts`.
Context: `PRD.md` § Frontend pages item 1 requires protected routes; the brief requires no flash of real data.
Alternatives: a `useEffect` redirect in each page (renders the page first, so an unauthenticated visitor to `/dashboard` sees a frame of real KPI numbers before being sent away - the exact failure the brief names); `getSession()` instead of `getUser()` (decodes the cookie and trusts it, so a hand-edited cookie claiming `hse_manager` would pass).
Rationale: middleware runs instead of the render, not after it. `getUser()` verifies the JWT with Supabase at the cost of one round trip per protected request. The `user_role.ts` split exists because `supabase_client.ts` builds a browser client at module load and throws there on missing env vars - importing it into the Edge runtime would drag both into a runtime that has neither.

### [Day 1 / Block 7] Span offsets are sliced by code point, not by UTF-16 unit - 2026-08-26
Decision: `buildReportSegments` slices `Array.from(text)`, not the string. Spans that cannot be sliced - reversed, negative, zero-width, out of range, non-integer, or overlapping one already emitted - are dropped rather than clamped.
Context: `span_start` / `span_end` are produced by Python, whose `len()` and slicing count code points. JavaScript's `String.prototype.slice` counts UTF-16 units.
Alternatives: plain `string.slice` (differs the moment a non-BMP character appears - one emoji shifts every later offset by one per surrogate pair and highlights the wrong words); clamping bad offsets into range (invents a highlight over text the model never pointed at).
Rationale: `Array.from` splits by code point, which matches Python exactly. Devanagari is inside the BMP so this costs nothing today and is correct anyway when a report carries an emoji. Dropping rather than clamping keeps the invariant that a malformed span list loses a highlight, never a character of text - asserted on 20 cases in `lib/precursor_spans_check.ts`.

### [Day 1 / Block 7] Two frontend dependencies, exact pins - 2026-08-26
Decision: `@supabase/supabase-js@2.112.4` and `@supabase/ssr@0.12.5`, both `--save-exact`. `tsconfig.json` gains `allowImportingTsExtensions` so the two self-checks run under plain `node`.
Context: `PRD.md` § Tech stack fixes Supabase as DB/Auth. `@supabase/ssr` is what supplies the cookie-based client middleware needs; `supabase-js` alone only offers a browser client that cannot read the request's cookies.
Alternatives: `supabase-js` alone with hand-rolled cookie handling (re-implements token refresh, the part most worth not writing); no state-management or component library was added, per the brief.
Rationale: two packages, both first-party, both required by the auth boundary. `noEmit` is on, so `allowImportingTsExtensions` never affects a build output - it only lets `node lib/precursor_spans_check.ts` resolve a relative import.

### [Day 1 / Block 7] `recharts@3.10.1` is the charting library, exact pin - 2026-08-26
Decision: one dependency, `recharts@3.10.1`, `--save-exact`, used only by `app/dashboard/rule_distribution_chart.tsx`.
Context: `PRD.md` § Frontend pages item 4 requires an IOGP rule distribution chart; Step 7B's brief requires a single lightweight charting library at an exact version.
Alternatives: hand-rolled SVG or CSS bars (genuinely viable for nine bars and zero bytes of dependency - rejected because the axis, tick and label geometry would be re-derived by Lane B on Day 2 for the next chart, and that is the point at which a hand-rolled chart layer stops being smaller than the library); Chart.js (canvas, so bars are invisible to a screen reader and untestable as markup); visx or D3 directly (a toolkit, not a chart - more code in our repo, not less).
Rationale: React-native SVG output, declarative, already React 19 compatible in its own peer range, and one import per chart element. SVG matters twice: it inherits the page's own accessibility handling, and it means the chart is inspectable markup rather than an opaque bitmap.

### [Day 1 / Block 7] The rule chart draws all nine bars in ONE hue, not nine - 2026-08-26
Decision: every bar is Tailwind blue-700 (`#1d4ed8`), horizontal layout, every value direct-labelled outside the bar end.
Context: nine IOGP rules with long names ("Safe Mechanical Lifting"), several of which are legitimately at zero on today's dataset.
Alternatives: nine categorical colours (spends the colour channel re-encoding what bar length already shows, and no nine-hue palette survives a colourblind-separation check - a generated ninth hue is indistinguishable from an existing one); vertical columns (forces the long rule names to 45-degree rotation or truncation); slate/rose/emerald from the existing palette (slate falls below the chroma floor and reads as grey at chart scale; rose and emerald are the reserved SIF verdict colours everywhere else in this UI, so reusing either would imply a verdict the chart is not making).
Rationale: the rules are nominal - no order, and no rule is a separate data series - so one hue is the correct encoding, not a compromise. `#1d4ed8` was checked against the six palette checks on a white surface rather than picked by eye (lightness band, chroma floor, over 3:1 contrast: all pass). Labelling every value outside the bar end is what makes a zero-count rule legible rather than merely present.

### [Day 1 / Block 7] The density table displays the rate and its two integers in one cell - 2026-08-26
Decision: `sif_rate` renders as a percentage with `sif_reports` of `total_reports` beside it, and `rank_score` is its own visible column. Sorting is local to the rows already fetched and never refetches; the default order is the backend's `rank_score` descending.
Context: `PRD.md` names this table the literal expected-outcome line of the problem statement.
Alternatives: showing the rate alone (a percentage with a hidden denominator cannot be audited - 100% of one report and 60% of forty look like the same kind of number); hiding `rank_score` as an implementation detail (then "why is 100% below 60%?" has no answer on screen); server-side sorting (a round trip per click for a re-order of rows already in the browser).
Rationale: every number on the screen can be divided back out by eye, and the one question this ordering always provokes is answered by a column rather than by a footnote. Keeping the Wilson-ordered view as the default - and reachable again by clicking `Ranking score` - means the defensible ordering is what a reader sees first and can always return to.

### [Day 1 / Block 9] PATTERNS.md names our own rule violations instead of documenting the aspiration - 2026-08-26
Decision: `PATTERNS.md` hands the four lanes the Boring Architecture rules AND lists the 8 files that currently break the ~200-line limit, the two docstrings whose commands do not run, and the lint command that does not exist. It also tells lanes to treat `frontend/lib/user_role.ts` and `frontend/lib/precursor_spans.ts` as frozen even though neither is on the FROZEN list yet, pending the integrator's call in `DIY.md`.
Context: this file is read by four people in separate agent sessions who cannot see the repo's history, and it is the only thing keeping them from inventing four architectures on the Day 1 baseline. It was written before Block 8, so it describes a codebase whose three inference bodies are still interim.
Alternatives: documenting the rules alone and omitting our violations (a lane finds a 313-line frozen file within an hour and reasonably concludes the limit is decorative, which costs more than the honesty does); listing the violations without restating the rule (reads as permission); waiting until after Block 8 so the interim bodies are gone (leaves Days 2-4 with no conventions document, which is the failure `STAGES.md` Block 9 explicitly warns about).
Rationale: a rule handed over with a known-violations list attached is enforceable; the same rule handed over as an aspiration a reader can falsify in one `wc -l` is not. Every violation is cross-referenced to the `AUDIT.md` entry that already accepted it, so a lane can tell recorded debt from an unlogged mistake. Freezing the two cross-lane files by instruction rather than by list is the conservative side of an unresolved decision: over-freezing costs a lane one `DIY.md` request, while under-freezing lets a silent edit to the privilege rule open the management view to an unclaimed account.

### [Day 1 / Block 9] The U+0000 guard goes in FROZEN `schemas.py`, at the trust boundary - 2026-08-26
Decision: a `strip_nul_bytes` field validator on `ReportCreate.raw_text` in `backend/schemas.py`, which removes U+0000 rather than rejecting the report. One `NUL_BYTE` module constant beside it. No change to any field name, type or nullability, so the wire contract is untouched.
Context: a report containing U+0000 returned a raw `HTTP 500` with a `text/plain` body from the running API (`AUDIT.md` 2026-08-26). Postgres cannot store the character (`22P05`); `routes/reports.py:_insert_report` catches only `23503`, so it escaped uncaught. `PRD.md` § Edge cases forbids both the crash and the raw 500. `schemas.py` is on the FROZEN list, but Block 5 defines that freeze as applying to Days 2-4 and this is Day 1 Mode A - logged here anyway because the file is contract-bearing, and raised in `DIY.md` for the integrator.
Alternatives: catching `22P05` in `_insert_report` alongside `23503` (turns the 500 into a clean 422, but only for the `reports` insert - `cleaned_text` and `entity_text` derive from the same field and would each need their own catch, three guards where the input has one source); stripping it in `preprocessing/clean_report.py` (that module owns text quality, not storability, and `raw_text` is written to the database unpreprocessed so the NUL would still reach the column); rejecting with a 422 instead of stripping (§ Edge cases says adversarial input earns a low confidence rather than a refusal, and U+0000 is invisible to whoever typed the report - a 422 would reject a genuine hazard report over a character its author cannot see); a database-level constraint or trigger (moves the rule into a migration nobody reviews, and fails the insert rather than accepting the report).
Rationale: every text column in the system derives from this one field - `cleaned_text` from it, `entity_text` sliced out of that - so a single guard at the point of entry is what makes all three storable, and it is the smallest diff that closes the whole class rather than the one path the bug was found on. Stripping keeps the report; the character carries no meaning a reader could have intended.

### [Day 1 / Block 9] The lone-surrogate fix goes in FROZEN `main.py` as an app-wide 422 handler - 2026-08-26
Decision: a `RequestValidationError` handler in `backend/main.py` that returns FastAPI's ordinary 422 body with unencodable characters scrubbed out, plus a small recursive `_scrub_unencodable`. Registered app-wide, not per-route. The 422 status and the `detail` list of `{loc, msg, type}` are unchanged.
Context: a JSON body containing the legal escape `\ud800` returned a raw `HTTP 500`. Pydantic's validation worked correctly - reporting it was what crashed, inside FastAPI's own `request_validation_exception_handler`, when `starlette/responses.py:201` called `.encode("utf-8")` on an error body echoing the rejected input (`AUDIT.md` 2026-08-26). `main.py` is FROZEN and is documented as app wiring only; an exception handler is app-level configuration rather than endpoint logic, which is why it belongs here and not in a router. Flagged in `DIY.md`.
Alternatives: extending the `schemas.py` strip to cover U+D800-U+DFFF (my first attempt, and WRONG - Pydantic rejects a lone surrogate while parsing the JSON string, so a field validator never runs and the code was dead; removed once measured); a middleware that rewrites the raw request body before parsing (has to re-encode every request to catch a case that arrives in almost none, and would silently alter input rather than reject it); registering the handler on the reports router only (every endpoint that echoes user input into a 422 shares the failure, so one handler covers `/review` and future routes for free); leaving it, on the grounds that only a hand-built body triggers it (a raw 500 on a projector is exactly what § Edge cases forbids, and "no ordinary client sends this" is not a property of an adversarial demo).
Rationale: fix the layer that actually fails. Scrubbing only the error body means valid input is never touched, and the check that proves it is a valid surrogate PAIR - an emoji - still round-tripping to storage. Keeping FastAPI's `detail` shape means `frontend/lib/api_client.ts:validationMessage` needed no change, verified against the real 422 rather than assumed.

### [Day 1 / Block 9] The demo seed ships 20 real rows, not 50 padded ones - 2026-08-26
Decision: `scripts/seed_demo_reports.py` seeds however many rows the checkpoint holds, prints the real number, and stops. Today that is 20. Rows are pushed through the real `POST /api/v1/reports` over HTTP; the only field the script writes directly is `submitted_at`, to spread the dates.
Context: `PRD.md` § Edge cases asks for ~50 pre-seeded reports as the demo-day network-lag fallback. `data/processed/localized.jsonl` holds 0 rows and `data/sample/localized.jsonl` holds 20, because the generation run has never been started (`AUDIT.md` 2026-08-26).
Alternatives: duplicating narratives up to 50 (inflates every dashboard denominator and every density rate is then computed over fabricated volume - the ranking table is the screen `PRD.md` calls the literal expected outcome, so corrupting its arithmetic to hit a row count is the worst available trade); pulling the 5 unique rows out of `data/scratch/` to reach 25 (`AUDIT.md` records that directory as experiment files and not a corpus, and unreviewed rows in demo data buy 5 rows at the cost of the provenance story); generating more rows first (Block 3 is blocked on quota, and Block 9 does not depend on it); writing rows straight to the tables with hand-made verdicts (they would not be real pipeline output, and would diverge silently the first time Lane C changes ingest).
Rationale: 20 real rows demonstrate the system; 50 rows of duplicated text demonstrate a row count. Going through the HTTP endpoint means these rows cannot drift from live ones as the ingest path changes, and it exercised the real pipeline hard enough to surface the U+0000 crash. The shortfall is logged as a number rather than hidden by padding.

### [Day 1 / Block 9] Seeded reports keep the dataset's own site, and get spread dates - 2026-08-26
Decision: each row is assigned to the site its own `site_name` field names, never redistributed. `submitted_at` is rewritten after ingest to a deterministic spread over 21 days using an uneven step pattern; `reporter_role` cycles 3:1 supervisor to manager.
Context: the brief requires a spread across sites and dates such that the density ranking has a meaningful non-uniform shape. The endpoint sets `submitted_at` to `now()` and takes no date from the client, correctly - it is a server-set field - so 20 rows landed within one minute.
Alternatives: round-robining rows across all 8 sites to flatten the distribution (each `raw_text` names its site in the prose and its `precursor_location` span points at those exact characters, so reassigning makes the text and the foreign key contradict each other, and the Magic View would highlight a location that disagrees with the report's own site); accepting one timestamp for every row (the dashboard then shows a single-day spike and any date filter is meaningless); letting the client send `submitted_at` (changes a frozen contract and lets any caller backdate a report); a random date per row (re-running the script would reshuffle the history, so no two runs are comparable).
Rationale: the resulting shape is real rather than arranged - 6 distinct `rank_score` values across 8 sites over 12 distinct days, with Moran's 1-of-1 at 100% correctly ranking below Naharkatiya's 2-of-3 at 67%. Rewriting one server-set field after the fact is the smallest deviation that gives the dashboard a history, and it is the only field the script touches outside the API.

### [Day 1 / Block 9] The empty-database case empties the real database, under a verified snapshot - 2026-08-26
Decision: `scripts/check_empty_database.py` snapshots all six tables to a file, re-reads and counts the snapshot before deleting anything, empties every table, runs the checks, then restores every row with its ORIGINAL id and verifies by id set. The snapshot file is deleted only after that verification passes, and deliberately kept on disk if it fails.
Context: `PRD.md` § Edge cases requires explicit empty states with no exception on any page. The database held 6 test reports, so the state could not be observed without moving them. Confirmed with the user before running, since it is the one destructive step in this block.
Alternatives: rendering components with hand-made empty props only (what the 2026-08-26 entry already did - it proves the components branch correctly but not that the API returns the empty shapes they expect, and the two together are the actual requirement); a separate throwaway Supabase project (a different database is not this database, and the check exists to test the real one); trusting the earlier component check plus reading the endpoint code (this is the "did I verify by running it" line in `AGENTS.md`, and the answer would have been no); deleting the 6 rows permanently (offered and not chosen - they are prior blocks' evidence); running it after seeding (26 rows to move instead of 6, for no gain).
Rationale: restoring by id rather than re-inserting is what makes this reversible - a matching row count with fresh uuids would leave every foreign key pointing at nothing, so the verification asserts the id SET, not the count. Ordering the cycle to include `users` came out of noticing `users.site_id` references `sites` with no cascade: without it the `sites` delete would have raised a foreign-key violation after `reports` was already empty. Caught by reading the schema before the first run rather than by breaking the database.

### [Day 1 / Block 9] Deploy configuration: root Dockerfile for HF Spaces, Vercel root-directory for the frontend — 2026-08-26
Decision: Backend ships as a container built from a **root** `Dockerfile` (`python:3.11-slim`, `COPY backend/ ./`, `uvicorn main:app --host 0.0.0.0 --port 7860`, non-root uid 1000) with the HF Spaces config in root `README.md` frontmatter (`sdk: docker`, `app_port: 7860`). Frontend deploys from the same repo with Vercel's Root Directory set to `frontend`. Three new files: `Dockerfile`, `.dockerignore`, `README.md`. No existing file changed, so no FROZEN file was touched.
Context: `PRD.md` § Tech stack allows Render/Railway/HF Spaces; the human's accounts (`DIY.md` Day 0) already cover Vercel + HF Spaces. An HF Space builds the Dockerfile at *its* repo root, and the Space is this repo pushed to a second remote — so the Dockerfile cannot live in `backend/`.
Alternatives: (a) Dockerfile in `backend/` — rejected, the Space would not find it without restructuring the repo into two repos, which breaks the single-repo lane/git model in `STAGES.md`. (b) Render/Railway with a native Python buildpack and no Dockerfile at all — genuinely fewer files, but the Day 0 account list names HF Spaces and a container is what survives the Block 8 `torch` addition without a platform migration. (c) `allow_origins=["*"]` — rejected outright, see below.
Rationale: `COPY backend/ ./` keeps the image free of everything else in the repo, so Vercel and the Space read the same commit without either seeing the other's tree. `app_port` and the `CMD --port` are the same number in two files by necessity; both carry a comment saying so. Nothing about the deploy is conditional on model weights.

### [Day 1 / Block 9] CORS stays an explicit origin allowlist, which blocks Vercel preview deployments — 2026-08-26
Decision: `FRONTEND_ORIGINS` is set to the single production Vercel origin. No wildcard, and no regex for `*.vercel.app`.
Context: `backend/main.py` already reads `FRONTEND_ORIGINS` (default `http://localhost:3000`); this deploy only supplies the value. The API carries the service-role key and has no authentication on any endpoint (`AUDIT.md` 2026-08-26, security, high).
Alternatives: `allow_origins=["*"]` — would make any page on the internet able to read and write every table through a visitor's browser. `allow_origin_regex` for preview URLs — expands the trusted set to anything Vercel ever hosts on that hash space, for a convenience the demo does not need.
Rationale: An open API is already a known high finding; adding a wildcard CORS policy on top of it converts "reachable by anyone who knows the URL" into "exploitable from any website a demo viewer visits". The cost is real and is stated rather than hidden: **preview deployments will fail CORS**, so the demo runs from the production URL. Adding one specific preview origin later is a value change, not a code change.
