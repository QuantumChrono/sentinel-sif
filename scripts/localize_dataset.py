"""Rewrite OSHA severe-injury narratives into Indian oil-rig reports, offline.

Run once by hand, never imported by anything under backend/.

Three jobs, kept strictly apart:
  - Python assigns sif_potential, by applying data/LABELING_RULE.md to OSHA's coded
    EventTitle/NatureTitle. Neither LLM stage sees the label or decides it.
  - LLM stage 1 rewrites prose only: Indian oil-rig context at the noise tier Python
    assigned. It is never asked for a label, a rule or a span.
  - LLM stage 2 reads the finished Indian narrative - not the OSHA original - and
    extracts iogp_rules plus four precursor substrings quoted from that narrative.
    Python turns those quotes into spans.

The split is deliberate. Asking one call to both rewrite prose and extract judgment
fields made the judgment fields hostage to prose wording: measured over four prompt
versions of the combined call, barrier-span coverage swung 19/20 -> 1/20 -> 14/20 ->
5/20 on wording changes alone, and IOGP coverage decayed 16/20 -> 6/20 as the rewrite
instructions grew. A stage that only extracts cannot be crowded out by rewrite rules.

The LLM is a fleet of models behind OpenAI-compatible endpoints - Groq's, plus Google's if
GEMINI_API_KEY is set - tried in order and rotated when one runs out of capacity. Narratives
go up BATCH_SIZE per request; each carries its own site, noise tier and mechanics, and a
response that comes back the wrong length or out of order is retried as a whole batch.

USE_TRINITY at the top routes every call to a self-hosted OpenAI-compatible endpoint instead,
which has no quota and so needs neither the fleet nor its pacing. Setting it False restores the
hosted path unchanged. Both backends share one request-and-validate function, so a misaligned
batch is rejected identically either way.

Usage:
  python scripts/localize_dataset.py --sample 20            -> data/sample/
  python scripts/localize_dataset.py --count 2500            -> data/processed/
Resumable: the output .jsonl is the checkpoint. Re-running skips OSHA IDs already in it.
"""

import argparse
import json
import os
import random
import re
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI

RAW_CSV = "data/raw/January2015toNovember2025.csv"

# The 8 seeded sites, copied from backend/schema.sql. Copied, not parsed: eight strings
# are more boring than a SQL parser, and this script must not import backend code.
SITES = [
    ("Duliajan", "Assam"), ("Naharkatiya", "Assam"), ("Moran", "Assam"),
    ("Baghjan", "Assam"), ("Makum", "Assam"), ("Hapjan", "Assam"),
    ("Tanot", "Rajasthan"), ("Ramgarh", "Rajasthan"),
]

# PRD.md § Glossary, canonical 9. Never rename, never merge, never add a tenth.
IOGP_RULES = [
    "Bypassing Safety Controls", "Confined Space", "Driving", "Energy Isolation",
    "Hot Work", "Line of Fire", "Safe Mechanical Lifting", "Work Authorisation",
    "Working at Height",
]

# ---------------------------------------------------------------------------
# data/LABELING_RULE.md § 5, verbatim. Do not edit a pattern here without
# re-running the § 9.10 title-inventory audit; a substring rule fails silently.
# ---------------------------------------------------------------------------
EXCLUDE_EVENT = [
    "shooting", "stabbing", "hitting kicking beating", "injury by other person",
    "object held or wielded by person", "self harm", "animal", "bites", "stings",
    "venomous", "assault", "restraining subduing",
]
A1_FALL = ["fall to lower level", "fall through surface", "jump to lower level"]
A1_NOT = "less than 6 feet"
A2_HIGH_ENERGY = [
    "falling object", "object falling", "flying object", "struck by object or equipment",
    "struck by dislodged", "struck by discharged", "struck by swinging",
    "suspended or swinging", "struck by powered", "struck by object dropped by person",
    "struck by rolling sliding or shifting", "struck by running powered",
    "struck by object falling from vehicle", "falling part of", "falling powered vehicle",
    "electric", "collision", "pedestrian struck by", "pedestrian vehicular",
    "rolling powered vehicle", "run over by", "nonroadway noncollision",
    "roadway noncollision", "jack knifed or overturned", "ran off driving surface",
    "part of occupant s body caught", "caught in running",
    "caught entangled in running", "caught in or compressed by",
    "compressed or pinched by shifting", "compressed between running equipment",
    "explosion", "fire", "ignition", "collapse engulfment", "engulfment in", "cave in",
    "collapsing structure", "inhalation of harmful substance",
    "exposure to other harmful substance", "exposure to harmful substances", "oxygen",
    "submers", "drown",
]
A3_BARRIER = ["curtailed by"]
B_LETHAL_NATURE = [
    "intracranial", "internal injur", "internal organs", "asphyxiation", "suffocat",
    "strangulat", "drown", "electrocution", "electric shock", "third or fourth degree",
    "spinal cord", "paralysis", "crushing", "multiple severe wounds", "hemorrhage",
    "multiple traumatic", "heat stroke",
]

# Hindi that is real code-switching reports the incident; Hindi that is decoration gets
# appended as advice. Naming the placement and the content, and never supplying wording,
# is what stopped both the parroting of prompt examples and the model's own stock phrase.
NOISE_CONTENT_RULE = (
    "Every Hindi clause must describe THIS incident - the task this worker was doing, the "
    "equipment in this report, the instruction actually given about this job, or what was "
    "actually said at the time. Put the Hinglish inside the account of what happened; do not "
    "append it to the end as advice. Never close with a general safety exhortation (telling "
    "people to be careful, to watch out, to mind safety), and never add a remark that "
    "contradicts the incident, such as saying everything was fine or nothing serious "
    "happened. Invent the wording yourself from this incident, do not reach for a stock "
    "oilfield phrase, and do not reuse a phrase you have already used for another report in "
    "this batch."
)

NOISE_INSTRUCTIONS = {
    "clean": (
        "Write it as a careful supervisor would type it: correct spelling, full words, "
        "plain professional English. No typos, no abbreviations, no Hindi."
    ),
    "moderate": (
        "Write it the way a busy field supervisor actually types on a phone. This voice is "
        "mandatory: the text MUST visibly carry a few genuine typos or transposed letters, "
        "some standard oilfield abbreviation, inconsistent capitalisation, and at least one "
        "clause written in Hindi in Roman script, mixed into the English sentences. Still "
        "fully understandable. " + NOISE_CONTENT_RULE
    ),
    "heavy": (
        "Write it as a rushed, barely-proofread field note. This voice is mandatory and is "
        "the messiest of the three: the text MUST carry frequent real typos, heavy oilfield "
        "abbreviation, missing articles and punctuation, run-on sentences, AND at least two "
        "full clauses written in Hindi in Roman script - not single borrowed words, whole "
        "clauses. A tidy, purely English, telegraphic note is NOT heavy noise and is wrong "
        "for this tier; a reader must be able to tell at a glance that this report is messier "
        "than the others. Messy, but a human HSE reader can still recover what happened. "
        + NOISE_CONTENT_RULE
    ),
}

BATCH_SIZE = 1  # narratives per request, in both stages. Index-matched by Python.
# 1, not 5: Groq's free tier caps 8,000 tokens/min, and a 5-row request overran that in a
# single call, so every batch spent its whole retry budget inside an already-closed window.
# A 1-row request is NOT small - measured from Groq's own 429 bodies on 2026-08-26 it is
# 3,251-5,467 tokens, because the prompt template (rules, noise tier, schema) dwarfs the
# narrative. Two stages per row is therefore ~7,000-11,000 tokens: still over 8,000/min for
# one model, which is why finishing a run depends on fleet rotation, not on batch size alone.
# The batch machinery (index-matched results, whole-batch retry) is left intact: it costs
# nothing at n=1 and raising this back is a one-line change if a paid tier lifts the cap.

# The model fleet, tried in order and rotated when one is exhausted. Every free tier here caps
# tokens-per-minute *and* tokens-per-day, so no single model can finish a 1,200-row run
# unattended: it stops at the daily wall partway through and waits for a human. Spreading the
# run across models is what lets it finish overnight.
#
# Re-verified on this account on 2026-08-28, by listing /v1/models on both endpoints and then
# issuing this script's exact call shape (json_object + max_completion_tokens) to every listed
# text model. A 429 counts as verified access, not a failure: it proves the model resolves on
# this key and only its per-minute window was spent at probe time, which is the same condition
# rotation exists to ride out. A 404 or "decommissioned" is what disqualifies a name.
#
# Withdrawn from Groq, confirmed again by 404/decommissioned: llama-3.1-8b-instant,
# llama-3.3-70b-versatile, qwen/qwen3-32b, moonshotai/kimi-k2-instruct, mixtral-8x7b-32768,
# deepseek-r1-distill-llama-70b. Gemini 1.5 and 2.x are likewise gone from this key.
#
# Four models that answered 200 are still left out, because reaching the fleet takes more than
# a successful HTTP call:
#   allam-2-7b            - Arabic-tuned. Returned valid JSON containing pseudo-Hinglish word
#                           salad ("woh trimester mein qrit karne laye jata tha"). A model can
#                           pass the transport check and fail the actual task.
#   groq/compound(-mini)  - not separate capacity. compound-mini's own 429 body named
#                           `openai/gpt-oss-120b`, so these route to the gpt-oss models already
#                           listed below and draw down the same quota they would fall back to.
#   gemini-robotics-er-*  - embodied-reasoning models. Untested on prose and the wrong tool.
# Floating aliases (gemini-flash-latest, gemini-flash-lite-latest, gemini-pro-latest) stay out
# for the reason they always did: an alias can change model underneath an unattended run.
#
# gpt-oss-safeguard-20b is a safety-classifier variant of the 20b, so the thing worth checking
# was refusal, not capacity: this dataset is entirely injuries and fatalities. It was given a
# fatal crushing narrative twice and both times returned clean Hinglish with no refusal and no
# moralizing, so it is in. If refusals ever do appear mid-run they arrive as a bad batch, which
# spends attempts without rotating - drop this name here rather than widening is_exhausted.
#
# gpt-oss-20b stays first because the prompts were measured against it. The rest are capacity
# fallbacks, not equals: prose quality across models is unverified, so rows produced after a
# rotation are worth a spot-check before they are trusted. The Gemini entries were spot-checked
# on one real narrative and returned clean Hinglish; full-size flash leads the lite variants,
# whose prose is thinner.
GROQ_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "openai/gpt-oss-safeguard-20b",
               "qwen/qwen3.8-27b", "qwen/qwen3.6-27b"]
GEMINI_MODELS = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
                 "gemini-3-flash-preview", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

# Project Trinity: a self-hosted OpenAI-compatible endpoint (30GB VRAM), reached over a
# Cloudflare tunnel. Flip USE_TRINITY to False and everything below behaves exactly as the
# hosted run does - the fleet, the rotation and the 429 pacing are bypassed, not removed.
#
# Bypassed rather than added to the fleet because Trinity has no quota: rotation, the 4s Groq
# pacing sleep and the retry_delay backoff all exist to survive a tokens-per-minute cap that
# does not apply here, and leaving them in place would only slow a run that has nothing to
# wait for. What Trinity does have is a tunnel that drops, which is a different failure with a
# different answer: wait for it to come back (see call_llm_trinity), never fall back.
#
# The URL is a trycloudflare quick tunnel, so it changes every time the tunnel restarts.
USE_TRINITY = False
TRINITY_BASE_URL = "https://pan-magazines-limitations-america.trycloudflare.com/v1"
# The non-thinking 7B, served on port 8081 behind the tunnel.
#
# This is the second switch, and it reverses the first. The 9B that replaced this model
# (trinity-chat-vision, port 8082) spent its budget inside hidden <think> tags and left too
# little for the JSON, so raising max_tokens funded the thinking rather than the answer. A
# non-thinking model spends the whole ceiling on visible output.
#
# Note what this model was moved away from, because it has not changed: left alone it runs
# past the closing brace and keeps writing prose. temperature 0.1 in TRINITY_PARAMS is what
# holds that down, and extract_json_object drops what gets through. If the JSON comes back
# clean but the Hinglish reads repetitive, that is this pairing's known cost - raise the
# temperature and let the parser absorb the trailing prose.
TRINITY_MODEL = "trinity-talk"
# Attempts for a response Trinity *answered* but the validator rejected. 5 matches the
# hosted path's budget for a one-model fleet. Unreachable is not counted here - that
# retries without limit, see call_llm_trinity.
TRINITY_BAD_BATCH_ATTEMPTS = 5

# The one call's tuning, per backend. Kept apart so Trinity's values cannot reach the hosted
# fleet, whose 1.0/4000 the prompts were measured against.
#
# max_tokens, not max_completion_tokens: Trinity's values replace the hosted key rather than
# joining it, because the two are different fields and sending both leaves which one caps the
# response up to whatever the local server prefers.
#
# 1200, raised from 600 on 2026-08-28 because 600 was the JSONDecodeError. The Kaggle logs put
# Trinity at 30.5 tok/s over a 21s call, which is ~640 generated tokens - i.e. the response was
# running into the cap, not rambling past a finished object. A cut-off response fails parsing
# and spends a bad-batch attempt, so this is a ceiling to raise if truncation persists, not a
# target to tighten; there is room to, since the hosted path's measured ceiling is 4000.
#
# 1200 buys more here than it did on the 9B: a non-thinking model spends none of it on hidden
# reasoning, so the whole ceiling reaches the JSON. Sized for BATCH_SIZE = 1; N narratives per
# request would need roughly N times this.
#
# temperature 0.1 buys clean JSON at the cost of variety in the prose (see the note in
# call_llm_trinity). Raise this first if the generated Hinglish starts repeating itself.
TRINITY_PARAMS = {"temperature": 0.1, "max_tokens": 1200}
FLEET_PARAMS = {"temperature": 1.0, "max_completion_tokens": 4000}

# Built here, once, so every batch reuses one connection pool. timeout is 600s, not the hosted
# fleet's 60s: on a hosted endpoint 60s means "stalled", but a local 30GB box generating 4,000
# tokens can legitimately take minutes, and a timeout there would discard finished work.
# max_retries=0 for the same reason as the fleet's - call_llm_trinity is the single retry
# authority, and an SDK-internal retry would hide the tunnel drop it needs to see.
TRINITY_CLIENT = (OpenAI(base_url=TRINITY_BASE_URL, api_key="trinity-local",
                         timeout=600.0, max_retries=0) if USE_TRINITY else None)

# ---------------------------------------------------------------------------
# STAGE 1 - prose only. This prompt must never mention IOGP rules or precursors:
# every instruction it carries competes for attention with the rewrite itself.
# ---------------------------------------------------------------------------
PROMPT_REWRITE = """You rewrite US industrial incident reports as Indian oil-and-gas field reports.

You are given {n} numbered reports. Rewrite every one of them, independently. Your only job
is the rewritten narrative - nothing is asked of you but prose.

PRESERVE THE MECHANICS OF EACH INCIDENT EXACTLY (a downstream safety label is derived from the
hazard and injury type listed with each report, so changing them corrupts the dataset): the
hazard or energy source, the way the barrier or control failed, and the outcome must all
survive your rewrite unchanged. Do not make an event safer, worse, or different. Do not invent
a fatality, and do not remove an injury that happened. You are relocating an incident, not
authoring a new one. Add no cause, no explanation and no detail the original does not state -
if the original says only that a component malfunctioned, jammed or failed, say exactly that
and no more, because inventing why it failed is a fabrication.

MECHANICS ARE NOT MATERIALS. The mechanics are the energy involved, the body part and injury,
the control that failed, and the severity. The workpiece, the material, the setting, the job
title and the person are all context, and you are required to change them. Swapping plywood
for a tool joint, a shop counter for a stores counter, or a domestic errand for a rig-floor
errand does NOT change the mechanics and does NOT corrupt anything, so long as the same energy
injures the same body part the same way. Keeping a US material or a US task in place because
you were told to preserve mechanics is the single most common way to get this wrong: preserve
the physics, replace the props.

RELOCATE THE WHOLE SCENE - do not merely prepend an Indian site name to a US narrative. No
US-context artifact may survive: no cash registers, customers, clerks, certified mail or
postal delivery, private residences, patients, sidewalks, driveways, lawns, or US job titles.
Every one of those must become its real equivalent in an Oil India-style onshore operation at
the site named in that report. Units are the one exception and are NOT a US artifact - see
QUANTITIES below.

THE WORK ITSELF MUST BE OILFIELD WORK, not merely the surroundings. Where the original task
has no place on a rig or in an oilfield - sanding plywood, serving at a retail till, delivering
mail, a domestic errand - replace the task with the nearest real oilfield job carrying the same
hazard and the same injury mechanism: a wire brush or bench grinder on a tool joint rather than
a sander on plywood, a stores and materials counter rather than a shop till, carrying paperwork
between the rig floor and the site office rather than postal delivery. The task, the equipment,
the surface and the material must all belong at that site. Name the site somewhere in the
narrative, so the report is locatable.

Choose an equivalent that keeps the same physics. The surface, substance or weather you use
must be one that genuinely occurs at the named site - monsoon mud, spilled drilling fluid, an
oil or grease film, loose sand, standing water. Never snow and never ice: neither occurs in
Assam or Rajasthan, and an ice slip at an Assam field is an obvious fabrication.

Where the original incident makes plain that a safety control was missing, bypassed or
defeated - equipment that started during maintenance, a fall with no fall protection, welding
without a permit, a load that was not secured, a walkway left fouled - say so plainly in the
narrative, as a normal part of the account, in grammatical English. Do not bolt it on as a
fragment. Where the original gives no sign of which control failed, say nothing about controls:
an invented control is worse than none.

QUANTITIES AND OBJECT CLASSES ARE COPIED, NOT CONVERTED. Reproduce every number in the
original exactly as it is written, with its original unit: 800 lb stays 800 lb, 2 inch stays
2 inch, 30 feet stays 30 feet. Do NOT convert to metric, do NOT round, and do NOT restate a
figure in a second unit. Mixed units are normal in an Indian field report, and an arithmetic
slip in a converted weight silently corrupts the incident. Never fabricate a quantity,
temperature, measurement, or metric that does not exist in the source text. If the original
states no quantity, do not invent one. Equally, never turn an object into a
different CLASS of object: a drum stays a drum and must not become a gas cylinder or any other
pressure vessel, a hand tool must not become a powered one, a ladder must not become a
scaffold. Quantities and object classes carry the mechanics of the incident, and the safety
label is derived from those mechanics.

Use Indian job titles (rig-in-charge, DSV, toolpusher, khalasi, fitter, rigger, HSE officer,
contract workman), Indian equipment habits (drawworks, workover rig, BOP, mud pump, DG set,
cellar pit, monkey board, sucker rod, tong, casing joint), and Indian names where a person is
named. Keep each rewrite 2-4 sentences, the same length ballpark as its own
original. Use only plain ASCII punctuation - ordinary hyphens and apostrophes, no typographic
dashes or quotes.

Follow the STYLE line of each report separately. The reports are deliberately not all in the
same voice, and blending them corrupts the dataset just as changing the mechanics does.

REPORTS:

{items}

Return ONLY a JSON object holding exactly {n} results, one per report, in the same order:
{{"results": [
  {{"index": the REPORT number this result rewrites,
    "localized_text": "the rewritten narrative, in that report's own style"}}
]}}
Never merge, drop, reorder, or invent a report."""

REWRITE_ITEM = """REPORT {index}
Hazard / energy source: {event_title}
Resulting injury type: {nature_title}
Rewrite into: {site}, {region}
STYLE: {noise_instruction}
ORIGINAL NARRATIVE: {narrative}"""

# ---------------------------------------------------------------------------
# EXPECTED BARRIER COVERAGE: roughly 8-10 of 20 rows, NOT 17. The OSHA source
# narratives do not name failed controls (AUDIT.md: a word-boundary scan of 20
# sources found 0 that do), so entailment from stated mechanics is the honest
# ceiling. Do NOT tune this prompt to raise the number - every earlier version
# that scored 14-19/20 got there by inventing a control and quoting itself.
# ---------------------------------------------------------------------------
# STAGE 2 - judgment fields only, read off the finished Indian narrative. It is
# never shown the OSHA original: the coded hazard and injury titles are enough
# to map a rule, and showing it US prose would put US wording back into spans it
# must quote verbatim.
# ---------------------------------------------------------------------------
PROMPT_EXTRACT = """You are an HSE analyst reading incident reports from an Indian onshore
oil-and-gas operation. You are given {n} numbered reports. For each one, extract structured
fields FROM THE REPORT TEXT. Do not rewrite, correct, translate, tidy or comment on any
report - the text is fixed and you only read it. Some reports are messy field notes with typos
and Hindi written in Roman script; read them as they are.

FOUR PRECURSOR SPANS. Each is either a substring copied character for character out of that
report's own text, or null. Never paraphrase, never tidy a typo, never merge two parts of a
sentence, and never quote from another report:
  - activity: the task that was underway when it happened
  - location: where it happened
  - equipment: the equipment, tool, vehicle or material involved
  - barrier_failure: the safety control that was missing, bypassed, defeated or inadequate

THE BARRIER FAILURE IS THE HARDEST FIELD. A SPAN IS EARNED ONE OF EXACTLY TWO WAYS.
WAY 1 - THE REPORT SAYS IT. The report's own words state that a control was missing, absent,
bypassed, defeated, removed or not applied. Quote that clause. This is reading, not inferring,
so it needs no further justification: "no guard", "the machine was unguarded", "bina harness",
"without a permit", "no pad under the jacking point", "lockout miss hua", "was not secured",
"the interlock had been removed" are all correct answers when the report actually contains
them. Look for absence stated in Hindi as readily as in English - "bina", "nahi", "nahi kiya"
attached to a control is the same statement.
WAY 2 - THE MECHANICS ENTAIL IT. The mechanics this report states ENTAIL that a specific
control was absent or defeated - where, given what the report says happened, that control
cannot have been in place. The canonical case: a motor, pump or machine that starts, moves or
energises while someone is working inside it or on it entails that energy isolation was not
applied, and the clause reporting that start-up is the span.
If neither way applies, return null. Way 1 does not loosen anything below: a control you had to
supply yourself is still a fabrication, and the words must be in the report you were given.
  Never infer a barrier from the OUTCOME. That someone was injured, how badly, and what kind
  of accident it was are not entailment: a fall does not by itself mean fall protection was
  missing, a machine injury does not by itself mean isolation was skipped, a burn does not by
  itself mean a permit was absent.
  Never return a GENERAL SAFETY OBSERVATION. That conditions were poor, that the job was
  rushed, that a surface was slippery, that housekeeping is often bad, or any advice about
  being careful is not a named control this incident shows was absent.
  Never INTRODUCE A CONTROL the report does not imply. Do not reach for LOTO, a permit, a
  guard, gas testing, a barricade, fall protection, PPE, an interlock, a spotter or a secured
  load unless this report's own mechanics require that it was missing or defeated. Do not
  upgrade "the throttle jammed" or "the equipment failed" into a missing inspection or a
  skipped maintenance schedule.
  It is never the injury, never the outcome, never the hazard itself, and never the worker's
  own movement: "fell", "slipped", "tripped", "struck", "caught", "crushed", "fractured",
  "amputated", "burned", "lost balance", "turned over", "jack-knifed", or any phrase naming
  what happened to the person or the equipment, is a wrong answer here.
MOST REPORTS DO NOT ENTAIL A BARRIER. Null is the correct and expected answer for the majority
of them, and costs nothing; a fabricated or outcome-shaped barrier is a defect. When you are
unsure, return null.

IOGP LIFE-SAVING RULES. Zero or more per report, copied EXACTLY from this list and nothing
else: {iogp_list}
Map a rule ONLY when the incident mechanism is what that rule governs, judged from the report
text together with the hazard and injury type given for it. Do NOT map a rule merely because
someone was injured, and do not reach for the nearest-sounding name:
  - Working at Height - a fall from height, or work on a scaffold, platform, monkey board,
    derrick or stairway at height. Not a slip, trip or fall on one level.
  - Energy Isolation - stored or live energy released during maintenance, cleaning, repair or
    adjustment: equipment that started or moved when it should have been isolated, electricity,
    stored pressure.
  - Hot Work - welding, cutting, grinding, flame, spark or other ignition source.
  - Line of Fire - the person was in the path of something moving, falling, swinging, rolling,
    escaping or under pressure: a dropped object, a released spray or jet, a shifting load, a
    pinch point on running equipment.
  - Safe Mechanical Lifting - a load being lifted, slung, hoisted, moved or stacked.
  - Driving - a vehicle in motion, including a rollover, a collision, or a fall from a moving
    vehicle. Not merely standing near a parked vehicle.
  - Confined Space - entry into a tank, vessel, cellar pit, sump or other confined space.
  - Work Authorisation - the job was done without the permit, authorisation or procedure it
    required.
  - Bypassing Safety Controls - a guard, interlock, alarm, trip or other protective device was
    defeated, removed or overridden.
An ordinary slip, trip or fall on a walking surface with nothing else involved maps to NO rule,
and an empty list is the right answer there. Several rules at once are correct when several
mechanisms are genuinely present - a dropped load that strikes someone is both Safe Mechanical
Lifting and Line of Fire.

REPORTS:

{items}

Return ONLY a JSON object holding exactly {n} results, one per report, in the same order:
{{"results": [
  {{
    "index": the REPORT number this result describes,
    "iogp_rules": ["zero or more, copied exactly from the list above"],
    "precursor_activity": "verbatim substring of this report's text, or null",
    "precursor_location": "verbatim substring of this report's text, or null",
    "precursor_equipment": "verbatim substring of this report's text, or null",
    "precursor_barrier_failure": "verbatim substring of this report's text, or null"
  }}
]}}
Never merge, drop, reorder, or invent a report."""

EXTRACT_ITEM = """REPORT {index}
Hazard / energy source: {event_title}
Resulting injury type: {nature_title}
REPORT TEXT: {text}"""


def normalize(column):
    """LABELING_RULE.md § 5 step 0. Skipping any part of this changes the labels."""
    return (column.fillna("").str.lower()
            .str.replace(r"[^a-z0-9 ]", " ", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip())


def contains_any(series, patterns):
    return series.str.contains("|".join(re.escape(p) for p in patterns), regex=True)


def load_labeled_frame():
    """Read the raw CSV and apply LABELING_RULE.md § 5. Returns the frame with labels."""
    df = pd.read_csv(RAW_CSV, dtype=str, keep_default_na=False, na_values=[""])
    event, nature = normalize(df["EventTitle"]), normalize(df["NatureTitle"])

    dropped = (contains_any(event, EXCLUDE_EVENT)          # E1 violence/animal/self-harm
               | df["ID"].duplicated(keep="first")          # E2
               | df["EventTitle"].isna() | df["NatureTitle"].isna()   # E3
               | df["Final Narrative"].str.len().lt(20))    # E4

    a1 = contains_any(event, A1_FALL) & ~event.str.contains(A1_NOT)
    a2 = contains_any(event, A2_HIGH_ENERGY)
    a3 = contains_any(event, A3_BARRIER)
    b = contains_any(nature, B_LETHAL_NATURE)

    frame = df.loc[~dropped, ["ID", "EventTitle", "NatureTitle", "Final Narrative"]].copy()
    frame = frame.rename(columns={"Final Narrative": "narrative"})  # itertuples needs no space
    frame["sif_potential"] = (a1 | a2 | a3 | b)[~dropped]
    frame["rule_hits"] = [
        ",".join(h for h, hit in (("A1", x1), ("A2", x2), ("A3", x3), ("B", xb)) if hit)
        for x1, x2, x3, xb in zip(a1[~dropped], a2[~dropped], a3[~dropped], b[~dropped])
    ]
    return frame


def pick_sample(frame, count, seed):
    """Half positive, half negative, seeded so a resumed run picks the same rows.

    A review sample, not the full-run sampling strategy — that is still undecided
    (LABELING_RULE.md § 10) and needs its own DECISIONS.md entry.
    """
    half = count // 2
    rng = random.Random(seed)
    rows = []
    for label, n in ((True, half), (False, count - half)):
        pool = frame.index[frame["sif_potential"] == label].tolist()
        rows += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(rows)
    return frame.loc[rows]


def assign_noise_tiers(n, seed):
    """Exactly the PRD distribution: 60% clean / 30% moderate / 10% heavy.

    Built as a fixed list and shuffled, not rolled per row — a per-row die gives
    ~60/30/10 with variance, and the PRD ratio is stated as exact.
    """
    heavy = round(n * 0.10)
    moderate = round(n * 0.30)
    tiers = ["heavy"] * heavy + ["moderate"] * moderate + ["clean"] * (n - heavy - moderate)
    random.Random(seed).shuffle(tiers)
    return tiers


# The model emits typographic punctuation (U+2011 non-breaking hyphen, U+2013 en dash) even
# when the prompt asks for ASCII - 2 of 20 rows in a measured sample. Prompting is the wrong
# tool for character-level compliance, so it is normalized here instead. Applied before
# find_span runs, so stored offsets are always taken from the normalized text a reader sees.
# Downstream tokenizers then see one hyphen character rather than three variants of it.
ASCII_PUNCTUATION = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2015": "-",
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2032": "'", "\u2033": '"', "\u2026": "...",
    "\u00a0": " ", "\u2007": " ", "\u2009": " ", "\u202f": " ", "\u00ad": "",
})


def to_ascii_punctuation(text):
    """Fold typographic dashes, quotes and spaces onto their ASCII equivalents."""
    return text.translate(ASCII_PUNCTUATION) if isinstance(text, str) else text


def find_span(text, quote):
    """Locate an LLM-quoted precursor in the final text. Python owns offsets, not the LLM."""
    if not quote or not isinstance(quote, str):
        return None
    start = text.find(quote)
    if start == -1:
        start = text.lower().find(quote.lower().strip())
        if start == -1:
            return None
        quote = text[start:start + len(quote.strip())]
    return {"text": quote, "start": start, "end": start + len(quote)}


# Audit diagnostic, kept as code because it got the answer wrong twice by hand. Two bugs it
# must not regress: (1) substring matching - a bare "ppe" matches inside "slipped" and
# "tripped", which is how a false "5/20 sources name a control" figure was produced; (2) an
# English-only list, which rejected the one genuine Hinglish barrier span we had ("bina lock
# off nahi karna chahiye"). Hence \b boundaries and Roman-script Hindi terms in the same list.
CONTROL_TERMS = [
    # English control nouns and absence phrasings
    r"ppe", r"lock", r"locks", r"locked", r"lockout", r"loto", r"tagout", r"isolat\w*",
    r"guard", r"guards", r"guarded", r"permit", r"permits", r"harness", r"lanyard",
    r"barricade\w*", r"handrail", r"railing", r"spotter", r"banksman", r"interlock\w*",
    r"gas test\w*", r"fall protection", r"not secured", r"unsecured", r"without",
    r"failed to", r"did not", r"was not", r"no one", r"never",
    # Roman-script Hindi: negation/absence markers and the control words they attach to
    r"bina", r"nahi", r"nahin", r"naa", r"band", r"khula", r"khuli", r"chalu",
    r"lagaya", r"lagayi", r"kiya", r"karna", r"chahiye", r"tha", r"thi",
]
CONTROL_PATTERN = re.compile(r"\b(?:" + "|".join(CONTROL_TERMS) + r")\b", re.IGNORECASE)


def names_a_control(text):
    """True if the text uses control language at all, on word boundaries.

    A coverage diagnostic, not a validator: it answers "could a barrier span plausibly be
    sourced from this text", never "is this span correct". Deliberately loose on the Hindi
    side - a negation marker counts - because a false positive here only widens what a human
    reads, while a false negative hides a real span, which is the failure that already
    happened once.
    """
    return bool(text) and bool(CONTROL_PATTERN.search(text))


# Substrings that mean a model is out of capacity. Matched on the message because the fleet
# spans two endpoints that disagree in wording, and because some quota errors arrive wrapped in
# a generic Exception with no status code left to read.
EXHAUSTED_MARKERS = ("rate limit", "rate_limit", "too many requests", "quota",
                     "resource_exhausted", "resource exhausted", "per day", "per-day")


def is_exhausted(error):
    """True if `error` means *this* model is out of capacity, so another model may still work.

    Distinct from a bad batch on purpose: a malformed or misaligned response says nothing about
    a model's quota, and rotating away on one would abandon a healthy model - while treating a
    per-day 429 as merely retryable is exactly the wall the fleet exists to get past.

    A 404 counts as exhausted too. A model withdrawn from the account is permanently out of
    capacity, and three of this script's originally planned models were withdrawn in precisely
    that way, so retrying one in place only burns the batch.
    """
    if getattr(error, "status_code", None) in (404, 429):
        return True
    text = str(error).lower()
    if "does not exist or you do not have access" in text:
        return True
    return any(marker in text for marker in EXHAUSTED_MARKERS)


def rotate_fleet(fleet):
    """Move the current model to the back, in place, so fleet[0] is always the next to try.

    Rotated in place and shared by every worker rather than copied per batch: a model that just
    returned a per-day 429 is exhausted for the whole run, not only for the batch that found
    out, so per-batch copies would each spend a wasted request rediscovering that. Nothing is
    dropped - a per-minute window reopens, so a model parked at the back is still worth reaching
    again later in a long run.
    """
    # ponytail: pop(0) and append are each atomic under the GIL, so concurrent workers can at
    # worst rotate twice, never tear the list. A lock would buy ordering nobody here needs.
    fleet.append(fleet.pop(0))


def build_fleet(pinned=None):
    """[(client, model)] in try order: Groq first, then Gemini if GEMINI_API_KEY is set.

    Groq leads because the prompts were measured against gpt-oss-20b. Gemini is appended rather
    than interleaved so a run only reaches a second vendor once the measured one is spent.

    timeout: 60s is above the slowest observed batch and far below a stall, so a hung request
    fails fast and the retry loop in call_llm_batch re-issues it. max_retries=0 keeps that loop
    the single retry authority, instead of each visible attempt silently becoming several inside
    the SDK - which against a rate-limited free tier is both fatal and invisible, and would also
    hide the 429 that rotation needs to see.
    """
    fleet = []
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        client = OpenAI(api_key=groq_key, timeout=60.0, max_retries=0,
                        base_url="https://api.groq.com/openai/v1")
        fleet += [(client, model) for model in GROQ_MODELS]
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        client = OpenAI(api_key=gemini_key, timeout=60.0, max_retries=0,
                        base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        fleet += [(client, model) for model in GEMINI_MODELS]
    if not fleet:
        raise SystemExit(
            "No GROQ_API_KEY or GEMINI_API_KEY in scripts/.env or backend/.env. See DIY.md - "
            "no call was made and no output was written."
        )
    if pinned:
        # --model pins one model, for reproducing a single model's output. Its client is
        # whichever vendor's key covers it; an unknown name is a typo worth failing on, since
        # discovering it after the run has started costs the whole batch.
        matches = [entry for entry in fleet if entry[1] == pinned]
        if not matches:
            raise SystemExit(f"--model {pinned!r} is not in the fleet. Available: "
                             + ", ".join(model for _, model in fleet))
        return matches
    return fleet


def retry_delay(error, attempt):
    """Seconds to wait before re-issuing a failed batch.

    Groq's 429 body states the real number ("try again in 22.99s") because the tokens-per-
    minute window only clears with wall-clock time. An exponential backoff starting at 1s is
    shorter than that hint, so every attempt lands inside the same exhausted minute and is
    spent without ever waiting long enough — which is how a 20-row sample lost 15 rows.
    """
    match = re.search(r"try again in ([\d.]+)s", str(error))
    if match:
        return float(match.group(1)) + 1.0  # +1s so we re-issue just after the window opens
    return 2 ** attempt + random.random()


def extract_json_object(text):
    """The JSON object in `text`: everything from the first { to the last }.

    Defensive, and a no-op on a well-formed response, which is why it runs for both backends
    rather than only for Trinity: the hosted fleet honours response_format and returns a bare
    object, so one parse path stays cheaper than two. Trinity's local server accepts
    response_format and then ignores it, which is what this exists for - it prefaces the object
    with conversational text, or wraps it in a ```json fence. Both are outside the braces, so
    both are dropped here and no separate fence handling is needed.

    Greedy to the LAST } on purpose: every response this script asks for nests objects inside
    `results`, so stopping at the first } would truncate all of them. The cost is that a } in
    trailing prose is swallowed too, which yields a parse error the caller retries rather than
    silently wrong data.

    A truncated response cannot be rescued here and is not meant to be: its outermost object
    never closes, so the last } found is an inner one, the result fails json.loads, and the
    caller retries. Truncation is fixed at max_tokens, not at the parser.
    """
    match = re.search(r"\{[\s\S]*\}", text or "")
    # No braces at all means the model answered with prose only. Returned as-is so the parse
    # error quotes what actually came back, instead of an empty string that says nothing.
    return match.group(0) if match else (text or "").strip()


def request_batch(client, model, prompt, count, required_field=None):
    """One JSON batch request, no retries. Returns (results, prompt_tokens, completion_tokens).

    Shared by both stages and by both backends: the failure modes are identical, and a
    misaligned response is as fatal in stage 2 as in stage 1, on Trinity as on Groq. The
    response is accepted only if it holds one result per input, each self-labelled with the
    index it describes - a short, long, or reordered batch raises, because a silently shifted
    result would attach one report's spans or narrative to another report's SIF label.

    Every failure leaves this function as an exception; deciding whether to rotate, wait or
    give up belongs to the caller, which is the only part that differs between backends.
    """
    # Keyed off the model name, the same way the pacing sleep below is. FLEET_PARAMS carries
    # the hosted path's measured 1.0/max_completion_tokens=4000: gpt-oss-120b is a reasoning
    # model, and a measured trivial call spent 91 of its 144 completion tokens on hidden
    # reasoning. A batch plus that overhead overran the endpoint's default ceiling and
    # truncated the JSON mid-document, which arrives as a 400 json_validate_failed or a short
    # results array. That ceiling is raised rather than reasoning_effort lowered, because the
    # reasoning is what strips US context and tells a barrier from an outcome.
    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        **(TRINITY_PARAMS if model == TRINITY_MODEL else FLEET_PARAMS),
    )
    # Parsing and validation raise from inside this function so the caller's retry covers
    # them too: a truncated or misaligned batch is as retryable as a 429, and neither may
    # reach the .jsonl half-accepted.
    body = extract_json_object(response.choices[0].message.content)
    results = json.loads(body)["results"]
    if len(results) != count:
        raise ValueError(f"asked for {count} results, got {len(results)}")
    for offset, result in enumerate(results):
        if result.get("index") != offset + 1:
            raise ValueError(
                f"result at position {offset} claims index {result.get('index')!r}")
        if required_field and not str(result.get(required_field) or "").strip():
            raise ValueError(f"result {offset + 1} has no {required_field}")
    usage = response.usage
    if model in GROQ_MODELS:
        # Trinity never reaches this: TRINITY_MODEL is not in GROQ_MODELS, and a local
        # model has no per-minute window to pace against.
        # Pace, don't burst: back-to-back calls stack inside one 8,000/min window and
        # 429 within a couple of rows. 4s takes the edge off that burst, but it does NOT
        # keep a single model under the cap - at a measured ~5,000 tokens per call, one
        # model sustains only ~1.6 calls/min, so staying under by pacing alone would
        # need ~37s here. Fleet rotation, not this sleep, is what lets a run progress;
        # this only reduces how often rotation is triggered. Raise it if 429s dominate.
        time.sleep(4)
    return results, usage.prompt_tokens, usage.completion_tokens


def is_tunnel_down(error):
    """True if `error` means Trinity could not be reached, rather than answered badly.

    A Cloudflare quick tunnel drops when the Kaggle notebook backing it restarts, and comes
    back at the same URL. That is worth waiting out; a malformed response is not, so the two
    are told apart and only this one retries without limit. Any 5xx counts, not just 502/503:
    Cloudflare also serves 520-530 for its own origin errors, and enumerating them invites the
    one that was missed to look like a bad batch and burn the batch's attempt budget.
    """
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    status = getattr(error, "status_code", None)
    return isinstance(status, int) and status >= 500


def call_llm_trinity(prompt, count, required_field=None):
    """call_llm_batch's body for USE_TRINITY: one local model, no rotation, no pacing.

    Trinity has no quota, so nothing here waits on purpose - the 4s Groq pacing sleep and the
    retry_delay backoff both exist to survive a tokens-per-minute cap that does not apply, and
    a tunnel drop is not answered by backing off from a server that is simply absent.

    Retries split by cause. Unreachable retries forever at 10s, because the tunnel returning is
    a matter of when, and giving up would fail rows a wait would have completed. A response the
    validator rejects retries only TRINITY_BAD_BATCH_ATTEMPTS times and then raises: a model
    that cannot produce this schema will not start, and an unbounded loop there would hang the
    whole run instead of letting the .jsonl checkpoint carry the batch to a later attempt.

    Those retries are weaker than they look, because TRINITY_PARAMS sets temperature 0.1. At the
    hosted path's 1.0 a re-issued batch is a genuinely different sample and often succeeds; near
    0 the model returns almost the same response, so five attempts at a truncation or a schema
    miss are close to five copies of one failure. Read a batch that exhausts them as "this
    prompt does not fit in max_tokens" or "this model cannot hold the schema", not as bad luck,
    and change the ceiling or the temperature rather than the attempt count.
    """
    bad_batches = 0
    while True:
        try:
            return request_batch(TRINITY_CLIENT, TRINITY_MODEL, prompt, count, required_field)
        except Exception as error:
            if is_tunnel_down(error):
                # No attempt counter on purpose: see the docstring. Ctrl-C is the way out.
                print(f"  Trinity unreachable: {type(error).__name__}: {error}")
                print("  waiting 10s for the tunnel, NOT falling back to Groq/Gemini")
                time.sleep(10)
                continue
            bad_batches += 1
            if bad_batches >= TRINITY_BAD_BATCH_ATTEMPTS:
                raise
            print(f"  retry {bad_batches}/{TRINITY_BAD_BATCH_ATTEMPTS - 1} on "
                  f"{TRINITY_MODEL}: {type(error).__name__}: {error}")


def call_llm_batch(fleet, prompt, count, required_field=None):
    """One batch through whichever backend is configured, with retries.

    USE_TRINITY routes to the self-hosted model and returns before `fleet` is ever read, so the
    rotation below is bypassed rather than altered. With USE_TRINITY False this is exactly the
    hosted path it always was: attempts are budgeted so a full pass over the fleet is always
    possible before a batch is given up on, while a one-model fleet keeps the five attempts
    this loop was measured with.
    """
    if USE_TRINITY:
        return call_llm_trinity(prompt, count, required_field)
    for attempt in range(len(fleet) + 4):
        client, model = fleet[0]
        try:
            return request_batch(client, model, prompt, count, required_field)
        except Exception as error:  # exhausted model / transient 5xx / bad batch - retry
            # A per-day quota is not transient: no backoff inside this run can clear it, and
            # every attempt spends another request. With no other model to move to, fail the
            # batch now and let the .jsonl checkpoint resume it once the quota rolls over.
            if len(fleet) == 1 and "per day" in str(error).lower():
                raise
            if attempt == len(fleet) + 3:
                raise
            print(f"  retry {attempt + 1} on {model}: {type(error).__name__}: {error}")
            if is_exhausted(error) and len(fleet) > 1:
                rotate_fleet(fleet)
                print(f"  WARNING {model} out of capacity, switching to {fleet[0][1]}")
                time.sleep(5)  # let the switched-to model's own window breathe before reuse
            else:
                # Not a capacity problem, so the same model is still the right one to ask.
                time.sleep(retry_delay(error, attempt))


def localize_batch(fleet, batch):
    """Both LLM stages for one batch of (row, tier). Returns (records, tokens_in, tokens_out).

    Stage 1 rewrites the prose. Stage 2 then reads only the rewritten Indian text - never the
    OSHA original - and extracts the judgment fields from it, so a span it quotes can only come
    from the text that is actually stored. Python normalizes punctuation between the stages and
    computes every offset afterwards, so raw_text[start:end] always round-trips.

    Two requests per batch roughly doubles the tokens per batch against the free tier's
    8,000/min, which is why --workers defaults to 1 and retry_delay honours the server's hint.
    """
    sites = [SITES[zlib.crc32(row.ID.encode()) % len(SITES)] for row, _ in batch]

    rewrite_items = "\n\n".join(
        REWRITE_ITEM.format(
            index=index + 1, event_title=row.EventTitle, nature_title=row.NatureTitle,
            site=site, region=region, noise_instruction=NOISE_INSTRUCTIONS[tier],
            narrative=row.narrative,
        )
        for index, ((row, tier), (site, region)) in enumerate(zip(batch, sites))
    )
    rewrites, in_1, out_1 = call_llm_batch(
        fleet, PROMPT_REWRITE.format(n=len(batch), items=rewrite_items),
        len(batch), required_field="localized_text",
    )
    texts = [to_ascii_punctuation(result["localized_text"]).strip() for result in rewrites]

    extract_items = "\n\n".join(
        EXTRACT_ITEM.format(index=index + 1, event_title=row.EventTitle,
                            nature_title=row.NatureTitle, text=text)
        for index, ((row, _), text) in enumerate(zip(batch, texts))
    )
    extracts, in_2, out_2 = call_llm_batch(
        fleet,
        PROMPT_EXTRACT.format(n=len(batch), items=extract_items,
                              iogp_list=" | ".join(IOGP_RULES)),
        len(batch),
    )

    records = []
    for (row, tier), (site, region), text, fields in zip(batch, sites, texts, extracts):
        record = {
            "id": row.ID,
            "site_name": site,
            "region": region,
            "raw_text": text,
            "noise_tier": tier,
            "sif_potential": bool(row.sif_potential),
            "sif_rule_hits": row.rule_hits,
            "osha_event_title": row.EventTitle,
            "osha_nature_title": row.NatureTitle,
            "osha_narrative": row.narrative,
            # Anything the model invented outside the canonical 9 is dropped, not renamed.
            "iogp_rules": [r for r in fields.get("iogp_rules") or [] if r in IOGP_RULES],
            "iogp_rules_rejected": [
                r for r in fields.get("iogp_rules") or [] if r not in IOGP_RULES],
        }
        for field in ("activity", "location", "equipment", "barrier_failure"):
            record[f"precursor_{field}"] = find_span(
                text, to_ascii_punctuation(fields.get(f"precursor_{field}")))
        records.append(record)

    return records, in_1 + in_2, out_1 + out_2


def verify_rule():
    """Re-derive LABELING_RULE.md § 7's published numbers and assert them.

    Exists because § 9.10 is explicit that a substring rule fails *silently*: the six
    broken A2 patterns produced a plausible percentage and a small era gap while
    mislabelling 1,775 rows. Any edit to a pattern list must re-run this.
    """
    frame = load_labeled_frame()
    positives = int(frame["sif_potential"].sum())
    checks = [
        ("labeling frame", len(frame), 103190),
        ("sif_potential true", positives, 68434),
        ("sif_potential false", len(frame) - positives, 34756),
        ("A1 falls", int(frame["rule_hits"].str.contains("A1").sum()), 13561),
        ("A2 high energy", int(frame["rule_hits"].str.contains("A2").sum()), 52527),
        ("A3 fall arrest", int(frame["rule_hits"].str.contains("A3").sum()), 64),
        ("B lethal nature", int(frame["rule_hits"].str.contains("B").sum()), 8878),
    ]
    # § 7's hand-checkable rows. 2015010015 is excluded by E1, so it must be absent.
    labels = frame.set_index("ID")["sif_potential"]
    examples = {"2015010016": True, "2015010018": False, "2015010019": True,
                "2015010253": True, "2015010517": True, "2015010025": False}
    checks += [(f"row {rid}", bool(labels[rid]), want) for rid, want in examples.items()]
    checks.append(("row 2015010015 excluded", "2015010015" in labels.index, False))

    tiers = assign_noise_tiers(1000, 1)
    checks += [("noise clean", tiers.count("clean"), 600),
               ("noise moderate", tiers.count("moderate"), 300),
               ("noise heavy", tiers.count("heavy"), 100)]

    # The offsets must round-trip: the UI highlights raw_text[start:end], so a span that
    # does not slice back to its own text would mis-highlight the Magic View.
    text = "The rigger was on the monkey board when the tong slipped."
    span = find_span(text, "on the monkey board")
    checks += [("span round-trip", text[span["start"]:span["end"]], "on the monkey board"),
               ("span text kept", span["text"], "on the monkey board"),
               ("span paraphrase rejected", find_span(text, "up on the derrick"), None),
               ("span null", find_span(text, None), None)]

    # A span must be locatable in the normalized text, and normalization must not smuggle a
    # non-ASCII character through: both are silent corruptions of the Magic View if they break.
    messy = to_ascii_punctuation("rig\u2011in\u2011charge \u2013 the DSV\u2019s call")
    checks += [("ascii punctuation folded", messy, "rig-in-charge - the DSV's call"),
               ("ascii punctuation is ascii", messy.isascii(), True),
               ("ascii punctuation keeps plain text", to_ascii_punctuation("plain - text"),
                "plain - text"),
               ("ascii punctuation passes None", to_ascii_punctuation(None), None)]

    # The control-language scan regressed twice: a substring "ppe" matched inside slipped /
    # tripped and invented a 5/20 figure, and an English-only list rejected a real Hinglish
    # barrier span. Both directions are asserted so neither can come back quietly.
    checks += [
        ("control scan not substring",
         names_a_control("worker slipped and tripped on the walkway"), False),
        ("control scan reads hinglish",
         names_a_control("bina lock off nahi karna chahiye"), True),
        ("control scan reads english", names_a_control("no LOTO was applied"), True),
        ("control scan ignores outcome",
         names_a_control("he fell and fractured his hip"), False),
        ("control scan passes empty", names_a_control(""), False),
    ]

    # The fleet must rotate away from an exhausted model and stay put on a bad batch: rotating
    # on a malformed response abandons a healthy model, while not rotating on a quota error is
    # the wall the fleet exists to get past. Both directions are asserted so neither regresses.
    class FakeError(Exception):
        def __init__(self, message, status_code=None):
            super().__init__(message)
            self.status_code = status_code

    checks += [
        ("exhausted reads 429", is_exhausted(FakeError("Rate limit reached", 429)), True),
        ("exhausted reads per-day", is_exhausted(FakeError("quota exceeded per day")), True),
        ("exhausted reads gemini", is_exhausted(FakeError("RESOURCE_EXHAUSTED")), True),
        ("exhausted reads withdrawn", is_exhausted(FakeError(
            "The model `x` does not exist or you do not have access to it.")), True),
        ("exhausted ignores bad batch",
         is_exhausted(ValueError("asked for 5 results, got 4")), False),
        ("exhausted ignores timeout", is_exhausted(FakeError("Request timed out")), False),
    ]
    # The extractor must find the object under any preamble or fence and must not corrupt a
    # clean response, since it runs on the hosted path's output too. The greedy match to the
    # last } is asserted directly: stopping at the first } would truncate every nested object
    # in `results`, which is the shape both stages actually return.
    checks += [
        ("json finds under fence",
         extract_json_object('```json\n{"a": 1}\n```'), '{"a": 1}'),
        ("json finds under preamble",
         extract_json_object('Sure! Here is the JSON:\n\n{"a": 1}'), '{"a": 1}'),
        ("json drops trailing prose",
         extract_json_object('```json\n{"a": 1}\n```\nHope that helps!'), '{"a": 1}'),
        ("json keeps nested objects",
         extract_json_object('{"results": [{"index": 1}]}'), '{"results": [{"index": 1}]}'),
        ("json passes clean json", extract_json_object('{"a": 1}'), '{"a": 1}'),
        # Truncation is not rescued here, by design: the outer object never closed, so what
        # comes back cannot parse and the caller retries. The fix for this is max_tokens.
        ("json leaves truncated body",
         extract_json_object('```json\n{"a": 1'), '```json\n{"a": 1'),
        ("json leaves prose only",
         extract_json_object('I cannot do that.'), 'I cannot do that.'),
        # The documented cost of matching to the LAST }: a brace in trailing prose is swallowed
        # too. That yields a parse error the caller retries, never silently wrong data.
        ("json overreaches past prose brace",
         extract_json_object('{"a": 1}\ndone {ok}'), '{"a": 1}\ndone {ok}'),
        ("json passes empty", extract_json_object(""), ""),
        ("json passes none", extract_json_object(None), ""),
    ]

    # Trinity's two failures must not be confused: an unreachable tunnel retries forever, so
    # reading a bad batch as unreachable would hang the run, and reading a dropped tunnel as a
    # bad batch would fail rows that a 10s wait would have completed.
    checks += [
        ("tunnel down reads 502", is_tunnel_down(FakeError("Bad gateway", 502)), True),
        ("tunnel down reads 503", is_tunnel_down(FakeError("unavailable", 503)), True),
        ("tunnel down reads 530", is_tunnel_down(FakeError("origin unreachable", 530)), True),
        # request=None: these carry no status_code, so the isinstance branch is what is being
        # asserted, and the SDK only stores the request without reading it.
        ("tunnel down reads timeout", is_tunnel_down(APITimeoutError(request=None)), True),
        ("tunnel down reads no connection",
         is_tunnel_down(APIConnectionError(request=None)), True),
        ("tunnel down ignores bad batch",
         is_tunnel_down(ValueError("asked for 1 results, got 0")), False),
        ("tunnel down ignores 400", is_tunnel_down(FakeError("json_validate_failed", 400)), False),
        ("tunnel down ignores 429", is_tunnel_down(FakeError("Rate limit", 429)), False),
    ]

    order = [("client", "first"), ("client", "second"), ("client", "third")]
    rotate_fleet(order)
    checks += [("fleet rotates to next", order[0][1], "second"),
               ("fleet parks exhausted last", order[-1][1], "first"),
               ("fleet drops nothing", len(order), 3)]

    failed = 0
    for name, got, want in checks:
        ok = got == want
        failed += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {name:26} got {got!r:<24} want {want!r}")
    print(f"\n{len(checks) - failed}/{len(checks)} passed")
    raise SystemExit(1 if failed else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-rule", action="store_true",
                        help="assert LABELING_RULE.md § 7's numbers; no API calls")
    parser.add_argument("--sample", type=int, help="review run: N rows into data/sample/")
    parser.add_argument("--count", type=int, help="full run: N rows into data/processed/")
    parser.add_argument("--out", help="write to this .jsonl instead of the default "
                                      "data/sample or data/processed path")
    parser.add_argument("--model", help="pin the run to one model from the fleet instead of "
                                       "rotating through all of them. For reproducing a "
                                       "single model's output; a pinned run stops at that "
                                       "model's daily quota")
    parser.add_argument("--target-id", help="generate these OSHA IDs only (one, or several "
                                            "comma-separated), bypassing the seeded sample "
                                            "draw. For re-testing one row, and for a targeted "
                                            "top-up of a rule the seeded draw under-supplied")
    parser.add_argument("--workers", type=int, default=1,
                        help="concurrent batches. Default 1: the free tier allows 8,000 "
                             "tokens/min and one batch costs ~4,000, so parallel batches "
                             "only manufacture 429s")
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--price-in", type=float, default=0.0, help="USD per 1M input tokens")
    parser.add_argument("--price-out", type=float, default=0.0, help="USD per 1M output tokens")
    args = parser.parse_args()

    if args.verify_rule:
        verify_rule()
    if bool(args.sample) == bool(args.count):
        parser.error("pass exactly one of --sample or --count")
    count = args.sample or args.count
    out_path = args.out or ("data/sample/localized.jsonl" if args.sample
                            else "data/processed/localized.jsonl")
    out_dir = os.path.dirname(out_path) or "."

    load_dotenv("scripts/.env")
    load_dotenv("backend/.env")
    if USE_TRINITY:
        # build_fleet is not called at all: it raises SystemExit without a Groq or Gemini key,
        # and a Trinity run legitimately has neither.
        if args.model:
            parser.error("--model pins a model in the Groq/Gemini fleet, which USE_TRINITY "
                         "bypasses. Set USE_TRINITY = False to use it.")
        fleet = None
        print(f"backend: Project Trinity {TRINITY_MODEL} at {TRINITY_BASE_URL}")
    else:
        fleet = build_fleet(args.model)
        print(f"fleet: {' -> '.join(model for _, model in fleet)}")

    print(f"applying LABELING_RULE.md to {RAW_CSV} ...")
    frame = load_labeled_frame()
    positives = int(frame["sif_potential"].sum())
    print(f"  frame {len(frame):,} rows | true {positives:,} "
          f"({positives / len(frame):.1%}) | false {len(frame) - positives:,}")

    if args.target_id:
        wanted = [i.strip() for i in args.target_id.split(",") if i.strip()]
        sample = frame[frame["ID"].isin(wanted)]
        missing = set(wanted) - set(sample["ID"])
        if missing:
            raise SystemExit(f"not in the labeled frame: {', '.join(sorted(missing))}")
        count = len(sample)
    else:
        sample = pick_sample(frame, count, args.seed)
    tiers = dict(zip(sample["ID"], assign_noise_tiers(len(sample), args.seed)))

    os.makedirs(out_dir, exist_ok=True)
    done = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as handle:
            done = {json.loads(line)["id"] for line in handle if line.strip()}
        print(f"  resuming: {len(done)} of {count} already in {out_path}")
    todo = [(row, tiers[row.ID]) for row in sample.itertuples() if row.ID not in done]
    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    print(f"  {len(todo)} rows to generate in {len(batches)} batch(es) of up to {BATCH_SIZE}")

    # Workers only return values; every write and counter update below happens on
    # the main thread as futures resolve, so no lock is needed.
    spent = {"in": 0, "out": 0, "ok": 0, "fail": 0}
    started = time.time()
    with open(out_path, "a", encoding="utf-8") as handle, \
            ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(localize_batch, fleet, batch) for batch in batches]
        for batch, future in zip(batches, futures):
            try:
                records, tokens_in, tokens_out = future.result()
            except Exception as error:
                spent["fail"] += len(batch)
                ids = ",".join(row.ID for row, _ in batch)
                print(f"  FAILED batch {ids}: {type(error).__name__}: {error}")
                continue
            spent["in"] += tokens_in
            spent["out"] += tokens_out
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()  # flush per row: a crash must not lose completed work
                spent["ok"] += 1
                cost = (spent["in"] * args.price_in + spent["out"] * args.price_out) / 1e6
                print(f"  [{spent['ok'] + len(done)}/{count}] {record['id']} "
                      f"{record['noise_tier']:8} sif={record['sif_potential']!s:5} "
                      f"tok {spent['in'] + spent['out']:,} ${cost:.4f}")

    cost = (spent["in"] * args.price_in + spent["out"] * args.price_out) / 1e6
    priced = f"${cost:.4f}" if args.price_in or args.price_out else "unpriced (pass --price-in/--price-out)"
    print(f"\nwrote {spent['ok']} rows ({spent['fail']} failed) to {out_path} "
          f"in {time.time() - started:.0f}s")
    print(f"tokens: {spent['in']:,} in + {spent['out']:,} out = "
          f"{spent['in'] + spent['out']:,} | cost: {priced}")


if __name__ == "__main__":
    main()
