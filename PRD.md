# PRD.md — SentinelSIF (engineering spec for the AI agent)

> This is the technical companion to the human-facing hackathon PRD (`PRD_SentinelSIF_SIH2026.md`). That doc has the pitch, demo script, and judging-criteria mapping — skip it unless you're asked to touch anything pitch-related. This file has everything relevant to what actually gets built. If this file and `DECISIONS.md` ever disagree, `DECISIONS.md` wins — it records what actually happened, this records what was planned.

## What this is
An AI/NLP pipeline that ingests free-text safety reports (OIL's UA/UC observations, near-misses, incidents) and:
1. Classifies each as SIF-potential vs non-SIF-potential (fatal-outcome potential, not observed severity)
2. Multi-label tags each against the 9 IOGP Life-Saving Rules
3. Extracts precursor entities (activity, location, equipment, barrier failure) via NER
4. Surfaces all of this in a dashboard ranking sites/activities by SIF-precursor density

## Glossary
- **SIF** — Serious Injury or Fatality: outcome-potential category, independent of what actually happened this time
- **UA/UC** — Unsafe Act / Unsafe Condition report
- **IOGP Life-Saving Rules (9, canonical, do not rename/merge)**: Bypassing Safety Controls, Confined Space, Driving, Energy Isolation, Hot Work, Line of Fire, Safe Mechanical Lifting, Work Authorisation, Working at Height
- **Precursor** — a condition/act/pattern statistically linked to fatal outcomes

## Architecture
```
[Next.js UI] -> [FastAPI backend] -> [Preprocessing] -> {SIF Classifier, IOGP Tagger, Precursor NER} -> [Supabase Postgres] -> [Next.js Dashboard]
```
All three model heads run inside a single synchronous inference request per report. No chained external API calls at inference time. LLM usage is confined to the offline synthetic-data generation script (Stage 2) — never called at runtime.

## Tech stack (do not substitute without a DECISIONS.md entry)
| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind |
| Backend | FastAPI (Python) |
| DB/Auth | Supabase (Postgres + Auth) |
| Classifier | DistilBERT, fine-tuned, binary + confidence |
| IOGP Tagger | Same/similar backbone, 9-way sigmoid multi-label head |
| Precursor NER | spaCy, custom entity ruler + optional fine-tune |
| Preprocessing | symspell/pyspellchecker + hand-built OIL acronym dict + Hinglish normalization pass |
| Deployment | Frontend: Vercel · Backend: Render/Railway/HF Spaces · DB: Supabase managed |

## Data strategy
- Source: OSHA Severe Injury Reports (public, downloadable, real free-text narratives + real severity outcomes)
- Localization: one-time offline LLM script rewrites narratives into Indian oil-rig context, injects controlled noise (typos/abbreviations/Hinglish at ~30% moderate / 10% heavy / 60% clean — not uniform)
- Target size: 2,000–3,000 synthetic records. Quality and label-consistency over volume.
- Labeling schema per record: `sif_potential` (bool, derived from a written rule against OSHA severity fields — the rule itself must be written down, not eyeballed), `iogp_rules` (list), `precursor_activity`, `precursor_location`, `precursor_equipment`, `precursor_barrier_failure` (text spans)
- Hold out ~15% as a test set before any training begins. Don't let the same LLM that generated the text also grade its own labels without a manual spot-check.

## ML pipeline detail
- **Preprocessing** (runs on every report): acronym expansion → spellcheck → Hinglish/Hindi normalization (graceful fallback to original text if normalization confidence is low — never let a bad normalization corrupt the input silently)
- **SIF Classifier**: binary + confidence float. Confidence < 0.65 (tune on validation set) → route to Manual Review Queue instead of auto-publishing.
- **IOGP Tagger**: multi-label (sigmoid, not softmax) — zero, one, or several rules per report
- **Precursor NER**: outputs (entity_text, entity_type, start_span, end_span), powers the highlighted-text UI. This is the explainability mechanism — no SHAP/LIME, deliberately (latency cost not worth it, NER highlighting looks equivalent to a judge/user)

## Backend API
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/reports` | Ingest report, runs full pipeline synchronously, returns result |
| GET | `/api/v1/reports` | List/filter (site, date range, sif_potential, iogp_rule, review_status) |
| GET | `/api/v1/reports/{id}` | Full detail: raw text, cleaned text, classification, tags, precursor spans |
| POST | `/api/v1/reports/{id}/review` | HSE officer confirms/overrides classification |
| GET | `/api/v1/analytics/density` | SIF-precursor density ranked by site and activity |
| GET | `/api/v1/analytics/rules` | Report count distribution across 9 IOGP rules |
| GET | `/api/v1/analytics/review-queue` | Reports below confidence threshold |

Ingest stays synchronous (submit → result in same request). No job queue — unnecessary complexity at this scale.

## Database schema (Supabase/Postgres)
```sql
sites (id uuid pk, name text, region text, latitude float, longitude float)

reports (id uuid pk, site_id uuid fk, raw_text text, cleaned_text text,
         language_detected text, reporter_role text, submitted_at timestamptz,
         status text)  -- 'processed' | 'processing_failed' | 'needs_review'

classifications (id uuid pk, report_id uuid fk, sif_potential boolean,
                  confidence float, model_version text, review_status text,
                  reviewed_by uuid null)  -- review_status: 'auto' | 'confirmed' | 'overridden'

iogp_tags (id uuid pk, report_id uuid fk, rule_name text, confidence float)

precursors (id uuid pk, report_id uuid fk, entity_type text, entity_text text,
            span_start int, span_end int)  -- entity_type: activity|location|equipment|barrier_failure

users (id uuid pk, name text, role text, site_id uuid fk)  -- role: hse_manager|site_supervisor|admin
```

## Frontend pages
1. **Login/Landing** — Supabase Auth, role-based redirect
2. **Report Intake** — text area + site selector, submit renders result inline (no navigation) — this is the demo's hero interaction, must feel instant
3. **Report Detail ("Magic View")** — highlighted text (color-coded by entity type), verdict badge + confidence, IOGP tag chips, Confirm/Override if below threshold
4. **HSE Dashboard** — KPI cards, IOGP rule distribution chart, **Site/Activity Density Ranking table** (the single most important screen — this is the literal "expected outcome" line from the problem statement, don't let it become an afterthought), recent high-risk feed
5. **Manual Review Queue** — low-confidence reports awaiting human call, Confirm/Override actions
6. Trends (Tier 2, only if time allows) — must be labeled "illustrative, synthetic data only," never framed as forecasting

## Feature tiering
**Tier 1 (must be demo-solid):** preprocessing, SIF classifier, IOGP tagger, precursor NER + highlighting, confidence-threshold review routing, density ranking dashboard, Intake + Detail pages.
**Tier 2 (only after Tier 1 is solid):** Trends page (clearly labeled illustrative), simulated in-app high-risk alert (never a real SMS/WhatsApp API call — demo-day failure risk), basic PII name redaction, near-duplicate detection.
**Cut, do not build, mention as scoped-out-on-purpose if asked:** WhatsApp/voice ingestion bot, general RAG chatbot over reports, time-series fatality forecasting, live model retraining during the hackathon.

## Edge cases (must be handled, not just noted)
- Empty/near-empty input → reject at API layer with validation message
- Very short valid report → expect low confidence → review queue, not a forced confident answer
- Mixed-script/heavy Hindi input → attempt normalization; low normalization confidence → pass original text through, flag `language_detected`, don't silently guess
- Multiple hazards in one report → multi-label tagger surfaces all applicable rules
- Adversarial/nonsense input → must not crash the pipeline; default to low confidence; never treat report text as an instruction anywhere downstream
- Model/inference failure → caught at API layer, `status = 'processing_failed'`, retry action in UI, never a raw 500 during a live demo
- Network lag on demo day → keep ~50 pre-seeded already-processed reports so Dashboard/Density views show something real even if live inference stalls

## Non-functional requirements
- End-to-end inference latency: under 3s, tested on actual demo hardware
- Dashboard load with 2,000–3,000 seeded reports: under 2s
- No hard dependency on a paid third-party API at inference time
- Desktop-first; tablet-responsive is nice-to-have, not required
