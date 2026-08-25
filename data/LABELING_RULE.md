# LABELING_RULE.md — how `sif_potential` is derived

**Status: written before any label exists.** Nothing in this repo has generated a
`sif_potential` value yet. This document is the rule; labels come after it is approved.

Applies to: `data/raw/January2015toNovember2025.csv` (105,996 rows, 28 columns — see
`data/raw/SOURCE.md` for provenance and SHA-256).

**Revision note (this pass).** Four changes, each argued below: a `Hospitalized >= 2`
positive test was **removed** (it decided the label from actual outcome, § 1.4); the decision
frame in § 1 was made **explicit** rather than left implicit in the pattern lists; **barrier
state** was given a defined role (§ 1.3, A3); and **six A2 patterns that never matched OSHA's
actual title strings were repaired**, recovering 1,775 rows the rule already intended to catch
(§ 5 A2, § 9.10). Needs a `DECISIONS.md` entry on approval.

---

## 1. The decision frame

From `PRD.md` § Glossary: **SIF is an outcome-*potential* category, independent of what
actually happened this time.** A dropped 300 kg load that misses everyone is positive. A
sprained ankle that put someone in hospital overnight is negative.

That definition is only reproducible if "potential" is broken into things an annotator can
actually check. Three questions, in order. **All three are about the situation; none is
about the injury that resulted.**

### 1.1 Was there a credible SIF exposure?

**A credible SIF exposure exists when a hazardous energy source was released, or could
release, at a magnitude a human body cannot absorb, and a person was within its reach.**

Two conditions, both required:

- **Magnitude** — the energy involved is *capable* of killing: gravity acting on a body or
  load over height, stored mechanical/rotational energy, vehicle momentum, electrical
  energy, pressure, thermal/combustion energy, or displacement of breathable atmosphere.
- **Proximity** — a person occupied the space that energy travelled into (the line of
  fire), whether or not it reached them.

Low-energy exposures fail this test *however unlucky the person was*. A same-level slip
cannot kill you at a different angle; a falling drill collar can. This asymmetry is what the
whole rule rests on.

### 1.2 Was there a plausible pathway to fatality or life-altering injury?

**A pathway is plausible when reaching a fatal or permanently disabling outcome from the
described situation requires only a change in ordinary circumstance — position, timing,
angle, or luck — and no additional independent failure.**

"Two feet to the left" is a plausible pathway. "If he had also been unconscious, and the
crane had also swung" is not. The test is *one variable*, not a chain of coincidences.

Note the deliberate scope: **fatality or life-altering injury**, so lethal energy is the
bar. An amputation is catastrophic and permanent but is usually not a fatality mechanism —
a hand in a rotating shaft rarely kills. It therefore does not qualify on its own; see the
asymmetry in Test B.

### 1.3 What was the state of the critical barrier or control?

A barrier is the thing standing between the energy and the person: machine guarding, energy
isolation/LOTO, fall protection, edge protection, exclusion zones, atmosphere testing,
permits.

**Barrier state raises the label, never lowers it:**

| Barrier state | Effect |
|---|---|
| Absent, bypassed, defeated, or failed while a person was exposed | **Positive.** The exposure was uncontrolled — the only reason this was survivable was chance. |
| Engaged and it held (the barrier is why the person lived) | **Positive.** The clearest possible SIF-potential case: the mechanism was fully present and a control absorbed it. |
| Intact and never loaded | Does not, by itself, make a case positive. |

A barrier that worked is **evidence of the hazard, not absence of it** — the single point
most often gotten backwards, and the previous version of this rule got it backwards (see A3).

**Honest limit on this criterion.** Barrier state is described in the narrative, which this
rule deliberately does not read (§ 2). OSHA's structured coding exposes it in only two
places, both used below: equipment running during maintenance/cleaning (energy isolation
absent) and fall-arrest engaged (fall protection loaded). Full barrier-failure detection is
assigned elsewhere in this system — `precursor_barrier_failure` spans and the *Bypassing
Safety Controls* / *Energy Isolation* IOGP labels (`PRD.md` § Labeling schema). It is not
claimed here.

### 1.4 Actual outcome severity does not determine the label

**Binding constraint: no positive test in this rule may read `Hospitalized`, `Amputation`,
or `Loss of Eye`.** Those columns count what happened to bodies. They are the definition of
outcome severity, and a rule that consults them to decide *potential* is circular.

This is enforced, not just asserted. A prior version of this rule contained a third positive
test — `Hospitalized >= 2`, on the theory that an event reaching two bodies released more
energy. Checked against the data, the 98 rows it alone decided were: contact with hot objects
(36), exposure through intact skin or eyes (23), `nonclassifiable` (7), **same-level slips and
trips (8)**, with injuries of second-degree burns, chemical burns and fractures. Two workers
with burnt forearms from an alloy-pot splash-back is a real injury event and not a fatality
pathway; two people slipping on the same wet floor is not one either. The test was labelling
on headcount. **Removed.** The cost is a named false negative (§ 9.8), which is the correct
place to pay it.

The reverse also holds: trivial observed injury never argues *against* a positive label.
Several worked examples in § 7 are positive with outcomes of "soreness, pain, hurt."

### The rule in one line

> A record is `sif_potential = true` if OSHA's coded event mechanism belongs to a
> **high-energy exposure class** (test A — § 1.1/1.2/1.3), **or** the coded nature of injury
> is one that **only lethal-grade energy transfer can produce** (test B). Otherwise
> `false`.

---

## 2. Columns that actually exist

Verified by reading the file, not assumed. All 28 columns:

`ID`, `UPA`, `EventDate`, `Employer`, `Address1`, `Address2`, `City`, `State`, `Zip`,
`Latitude`, `Longitude`, `Primary NAICS`, `Hospitalized`, `Amputation`, `Loss of Eye`,
`Inspection`, `Final Narrative`, `Nature`, `NatureTitle`, `Part of Body`,
`Part of Body Title`, `Event`, `EventTitle`, `Source`, `SourceTitle`, `Secondary Source`,
`Secondary Source Title`, `FederalState`

**Free-text narrative:** `Final Narrative` — the only free-text field. 0 nulls; length min 4,
median 182, mean 199, max 2,134 characters; 3 rows under 20 chars.

**Severity outcome columns:** `Hospitalized`, `Amputation`, `Loss of Eye`. These are
**counts of people, stored as decimal strings** (`"0.00"`, `"1.00"`, `"2.00"`) — not
booleans. Observed maxima: Hospitalized 6, Amputation 2, Loss of Eye 1. Distribution:

| Hospitalized | Amputation | Loss of Eye | rows |
|---|---|---|---|
| >0 | 0 | 0 | 78,001 |
| 0 | >0 | 0 | 20,148 |
| >0 | >0 | 0 | 7,812 |
| >0 | 0 | >0 | 27 |
| 0 | 0 | >0 | 7 |
| >0 | >0 | >0 | 1 |

**Every row has at least one severity flag greater than zero** (zero all-zero rows) —
because having one is what legally triggered the report. These columns cannot discriminate
anything, which is a second, practical reason § 1.4's ban costs nothing.

**Columns the rule uses: `EventTitle` and `NatureTitle`. Nothing else.** No outcome-severity
column appears anywhere in step 2.

### Why the rule never reads the narrative

The narratives are about to be LLM-rewritten into an Indian oil-rig context. If the label
were derived from text, and the text then changed, label and text could silently drift apart
— and the honest answer to *"how do you know this label is right?"* would degrade into
*"the model read it."* Deriving labels **only from OSHA's structured coding** means every
label traces to a field a U.S. safety regulator populated, is reproducible by hand in a
spreadsheet, and survives the rewrite untouched. The price is § 1.3's limit on barrier
detection, paid knowingly.

### A column that does not exist

There is **no fatality, death, or outcome-severity-grade column.** Confirmed: no column name
contains "fatal", "death", or "dead".

---

## 3. The fatality problem (read this before questioning the rule)

OSHA runs **two separate reporting channels** (from the program's own page, quoted in
`SOURCE.md`): hospitalizations, amputations and eye losses are **24-hour** reports — this
dataset. Employees **killed on the job are 8-hour reports, a different stream.**

**This dataset is, by construction, the set of severe injuries where the worker survived.**
Keyword scan of all 105,996 narratives: `fatal` 8, `died` 7, `killed` 3, `deceased` 1.

Two consequences, both unavoidable and both stated plainly rather than papered over:

1. **`sif_potential` cannot be a lookup of an observed fatality.** There is nothing to look
   up. It must be a *mechanism-based proxy* — which is what § 1 defines and what the PRD
   asks for.
2. **The rule cannot be statistically validated against fatal outcomes inside this file.**
   Its defensibility rests on the reasoning being explicit, deterministic, and inspectable —
   not on a measured correlation with deaths. Anyone who claims otherwise about this dataset
   is wrong.

*(The energy-based framing in § 1.1 is the standard industrial approach to SIF prevention. A
specific published energy threshold is deliberately not cited, because none was verified
against a source in this session.)*

---

## 4. Two structural landmines in this file

Both were found by inspection and both would silently corrupt labels.

### 4.1 OSHA changed OIICS versions mid-dataset — the numeric codes are not comparable

Rows from **2024 onward use OIICS v3**; rows from **2015–2023 use the older version**. The
same numeric code means different things in the two eras. Measured:

| Code | 2015–2023 means | 2024+ means |
|---|---|---|
| `Nature` 111 | Fractures (28,513 rows) | *(unused)* |
| `Nature` 124 | Hernias due to traumatic incidents (237) | **Fractures (6,323)** |
| `Nature` 1311 | Amputations (23,449) | *(unused)* |
| `Nature` 1220 | Cartilage fractures and tears | **Amputations (2,924)** |
| `Event` 2412 | Pedestrian struck in work zone | **Animal transportation collision** |

Of 113 `Event` codes appearing in both eras, **110 map to a different title.** Of 70
`Nature` codes in both eras, **54 differ.**

> **Rule consequence: never branch on `Event`, `Nature`, `Source`, or `Part of Body`
> numeric codes.** A rule keyed on `Nature == "111"` would label 2024–25 records against the
> wrong injury type entirely. **Only the `*Title` text columns are used**, because the text
> says what it means in both eras.

### 4.2 The title strings are dirty and era-dependent

- **Leading whitespace on 2024+ titles.** 17,863 rows have an `EventTitle` starting with a
  space: **17,745 from 2024–2025**, plus 118 stragglers in the old era (117 in 2023, 1 in
  2020). Every 2024–25 row with a non-null `EventTitle` has one — the single exception is the
  null-title row already dropped by E3. So whitespace is *nearly* an era marker but not
  exactly one: the 118 early rows carry v2 codes (`Nature 1311` Amputations, `Nature 111`
  Fractures), so **the era boundary is the event year, never the whitespace.** Raw distinct
  `EventTitle` values: 649. After full step-0 normalization: **540** — so **109 values are
  duplicates differing only in spacing or punctuation.** (Collapsing whitespace and case
  alone gets only to 569; the punctuation pass removes the remaining 29. Both halves of
  step 0 are load-bearing.)
- **Fall-height bands were re-bucketed.** 2015–2023 has `6 to 10 feet`, `11 to 15`,
  `16 to 20`, `21 to 25`, `26 to 30`; 2024+ collapses these into `6 to 30 feet`. The **only
  height distinction portable across both eras is `less than 6 feet` vs. everything else.**
- **Whole phrasings were replaced.** `caught in running equipment or machinery…` (13,989
  rows) is v2-only; 2024+ says `caught, entangled in running powered equipment…`. A rule
  matching only the first silently labels every 2024+ machine entanglement negative.

Step 0 below exists to defuse all of this.

---

## 5. The rule

Deterministic. No model, no randomness, no thresholds tuned on an outcome. Applied to
`EventTitle` and `NatureTitle` only.

### Step 0 — normalize (mandatory; skipping it changes the answer)

For `EventTitle` and `NatureTitle`, in this order:

1. Treat a missing value as the empty string.
2. Lowercase.
3. Replace every character that is not `a–z`, `0–9`, or a space with a single space.
4. Collapse runs of whitespace to one space; trim the ends.

`" Caught, entangled in running powered equipment  normal operation"` becomes
`"caught entangled in running powered equipment normal operation"`.

All patterns below are matched as **plain substrings** against these normalized strings.

### Step 1 — exclusion frame (drop before labeling, do not label `false`)

Drop a row if **any** of these hold:

| # | Condition | Rows |
|---|---|---|
| E1 | Normalized `EventTitle` contains any of: `shooting`, `stabbing`, `hitting kicking beating`, `injury by other person`, `object held or wielded by person`, `self harm`, `animal`, `bites`, `stings`, `venomous`, `assault`, `restraining subduing` | 2,797 |
| E2 | `ID` already seen earlier in the file (keep first) | 5 |
| E3 | `EventTitle` or `NatureTitle` is null | 1 (`ID 20251111222`) |
| E4 | `Final Narrative` shorter than 20 characters | 3 |

**Total dropped 2,806 → labeling frame = 103,190 rows.**

E1 removes workplace violence, animal attacks and self-harm. These are real severe injuries
but they have no counterpart in an oil-rig HSE observation stream and no IOGP Life-Saving
Rule addresses them; keeping them would teach the classifier vocabulary the deployed system
never sees. E2/E3/E4 are data hygiene. Dropping is *not* labeling negative — a dropped row
never reaches the dataset in either class.

### Step 2 — positive tests (OR; either one is sufficient)

#### Test A — high-energy exposure mechanism (from `EventTitle`)

A is the operational form of § 1.1 and § 1.2: each pattern names a mechanism where lethal
energy reached a person's space. Membership is by mechanism, so the label does not move with
how well the person happened to fare.

**A1 — falls to a lower level.** Contains any of `fall to lower level`,
`fall through surface`, `jump to lower level`, **and does NOT contain** `less than 6 feet`.
→ **13,561 rows.** (4,378 sub-6-foot falls are carved out by that exclusion; 643 of them
return via B.)

**A2 — other high-energy classes.** Contains any of:

```
falling object                  object falling                  flying object
struck by object or equipment   struck by dislodged             struck by discharged
struck by swinging              suspended or swinging           struck by powered
struck by object dropped by person              struck by rolling sliding or shifting
struck by running powered       struck by object falling from vehicle
falling part of                 falling powered vehicle
electric                        collision                       pedestrian struck by
pedestrian vehicular            rolling powered vehicle         run over by
nonroadway noncollision         roadway noncollision
jack knifed or overturned       ran off driving surface         part of occupant s body caught
caught in running               caught entangled in running     caught in or compressed by
compressed or pinched by shifting                               compressed between running equipment
explosion                       fire                            ignition
collapse engulfment             engulfment in                   cave in
collapsing structure            inhalation of harmful substance
exposure to other harmful substance                             exposure to harmful substances
oxygen                          submers                         drown
```

→ **52,527 rows.**

**A3 — barrier engaged and loaded.** Contains `curtailed by` (the OSHA title is
`fall or jump curtailed by personal fall arrest system`). → **64 rows, 55 of them reached by
no other test.**

A3 is § 1.3 applied literally, and it corrects a real error. A worker who fell from the
derrick and was caught by his SRL sustained "cuts and abrasions"; under the previous version
of this rule **52 of these 64 rows were labelled negative**, because the barrier did its job
and the injury was minor. That is the exact inversion this document exists to prevent: the
fall happened, the height was real, and a lanyard is the only reason there is a survivor to
report. **Fall protection that arrests a fall is proof of a fall from height, not proof of
safety.**

**Barrier reasoning already inside A2** (no label change; stated so the rationale is
inspectable rather than implicit): `caught in running equipment or machinery during
maintenance cleaning` (5,298 rows) and `struck by running powered equipment during
maintenance cleaning testing` (1,599) are positive *because* equipment turning under a
person's hands during maintenance means the energy-isolation barrier was absent or defeated —
6,897 rows whose positive label § 1.3 independently justifies.

**A = A1 ∪ A2 ∪ A3 = 65,721 rows.**

Each pattern was audited against the real title inventory before being included. Examples of
what they catch: `fire` → 572 rows across 14 titles, all genuine fire events (`vehicle or
machinery fire`, `flash fire`, `nonstructural fire n e c`); `excavation or trenching cave in`
and `collapse engulfment open trench or excavation` are reached via `cave in` and `collapse
engulfment`; both the v2 and v3 machine-entanglement phrasings are covered by the two
`caught…running` patterns.

Two candidate patterns were **tested and rejected**, recorded so the omissions are not read
as oversights:

- `pressure` — matches `exposure to change in water pressure` and `rubbed or abraded by
  friction or pressure`, neither high-energy. `explosion of pressure vessel piping or tire`
  (283 rows) is already caught by `explosion`.
- `normal operation` — looks barrier-related, is not. It would add 504 rows, almost all
  `fall or jump from vehicle in normal operation nonroadway`: routine vehicle egress, a
  same-level-class event, not a defeated control. Rejected.

**Six patterns were added after an audit found them missing** (`suspended or swinging`,
`falling part of`, `falling powered vehicle`, `rolling powered vehicle`, `run over by`, and
`pedestrian struck by` widened from `pedestrian struck by vehicle`). Each was a phrasing bug,
not a judgment call: A2 already claimed vehicle strikes and suspended loads as high-energy,
but the substrings did not match OSHA's actual titles — `pedestrian struck by vehicle` never
fires against `pedestrian struck by forward moving vehicle in work zone`, because "forward
moving" sits in the middle. **1,775 rows were labelled negative by a mechanism the rule
already intended to catch**, including 641 pedestrians struck by moving vehicles and 308
workers run over by rolling powered vehicles. See § 9.10 — this class of bug is silent, and
the audit that catches it is inspecting the title inventory, never re-reading the pattern
list.

#### Test B — injury only lethal-grade energy can produce (from `NatureTitle`)

**B is not a severity grade and must not be read as one.** It does not ask "how badly was
this person hurt." It asks the § 1.1 question backwards: *what magnitude of energy transfer
is required to produce this injury at all?* An intracranial bleed, a severed spinal cord, or
asphyxiation cannot be produced by a low-energy exposure — the injury is physical evidence
that lethal-grade energy was present, which is why it is admissible under § 1.4 while a
hospitalization count is not.

Contains any of:

```
intracranial      internal injur    internal organs   asphyxiation      suffocat
strangulat        drown             electrocution     electric shock
third or fourth degree              spinal cord       paralysis         crushing
multiple severe wounds              hemorrhage        multiple traumatic
heat stroke
```

→ **8,878 rows**, of which **2,713 are not already caught by A.**

B's job is to catch high-energy events whose `EventTitle` was coded vaguely (e.g.
`nonclassifiable`, 788 rows) but whose injury pattern proves the energy present.

**The amputation asymmetry, which is the test of whether B is really energy-based.**
`Amputations` is one of the most severe entries in the whole `NatureTitle` vocabulary and it
is **deliberately excluded from B.** Per § 1.2 the bar is a fatality or life-altering
pathway, and a finger taken by a deboning machine is permanent but not a lethal mechanism. A
severity-ranking test would rank amputation near the top; an energy test does not include it.
An amputation reaches positive only when the *event* was high-energy (test A). Measured: of
27,722 `amputations` rows in the frame, **21,700 are positive** because the event that took
the limb was high-energy, and **6,022 are negative** because it was not — every one of them
decided on mechanism, none on the fact of the amputation.

### Step 3 — default

Any row in the frame matching neither A nor B → **`sif_potential = false`.**

---

## 6. Reference implementation (spec, not the pipeline)

Runnable so a reviewer can reproduce the numbers in § 7. It is **not** the localization
script and nothing imports it. The list literals are the pattern blocks above, verbatim.

```python
import pandas as pd

FALL   = ['fall to lower level', 'fall through surface', 'jump to lower level']
ARREST = ['curtailed by']
A2     = [...]   # the A2 block above, verbatim
B      = [...]   # the B block above, verbatim
EXCL   = [...]   # the E1 list above, verbatim

def normalize(col):
    return (col.fillna('').str.lower()
               .str.replace(r'[^a-z0-9 ]', ' ', regex=True)
               .str.replace(r'\s+', ' ', regex=True).str.strip())

df = pd.read_csv('data/raw/January2015toNovember2025.csv', dtype=str,
                 keep_default_na=False, na_values=[''])
event, nature = normalize(df['EventTitle']), normalize(df['NatureTitle'])
any_of = lambda s, pats: s.str.contains('|'.join(pats), regex=True)

dropped = (any_of(event, EXCL) | df['ID'].duplicated(keep='first')
           | df['EventTitle'].isna() | df['NatureTitle'].isna()
           | df['Final Narrative'].str.len().lt(20))

event, nature = event[~dropped], nature[~dropped]
a1 = any_of(event, FALL) & ~event.str.contains('less than 6 feet')
a2 = any_of(event, A2)
a3 = any_of(event, ARREST)
b  = any_of(nature, B)

sif_potential = a1 | a2 | a3 | b     # no outcome column appears here, by § 1.4
```

---

## 7. Measured output on all 105,996 rows

Real numbers, computed — not estimates.

| | rows | share of frame |
|---|---|---|
| Excluded (step 1) | 2,806 | — |
| **Labeling frame** | **103,190** | 100% |
| `sif_potential = true` | **68,434** | **66.3%** |
| `sif_potential = false` | **34,756** | **33.7%** |

Test contribution: A1 13,561 · A2 52,527 · A3 +55 new · **A total 65,721** · B +2,713 new.

**Era stability** — the strongest available evidence the rule is not accidentally keyed to
one OIICS version:

| Era | % positive | rows |
|---|---|---|
| 2015–2023 (v2) | 66.5% | 86,098 |
| 2024–2025 (v3) | 65.6% | 17,092 |

A 0.9-point gap across a full taxonomy change indicates the rule reads mechanism, not
encoding. Had it been keyed to numeric codes or v2-only phrasings, this gap would be huge.
(Before the A2 repair the gap was 2.2 points — the missing patterns were era-skewed, so
fixing them tightened this too.)

**Worked examples** (real rows, hand-checkable):

| ID | normalized `EventTitle` | `NatureTitle` | A | B | label |
|---|---|---|---|---|---|
| 2015010015 | `injured by physical contact with person while restraining subduing…` | — | — | — | **excluded** (E1) |
| 2015010016 | `ignition of vapors gases or liquids` | — | **A2** | no | **true** |
| 2015010018 | `other fall to lower level less than 6 feet` | not in B | no | no | **false** |
| 2015010019 | `caught in or compressed by equipment or objects unspecified` | soreness, pain, hurt | **A2** | no | **true** |
| 2015010253 | `fall or jump curtailed by personal fall arrest system` | cuts and abrasions | **A3** | no | **true** |
| 2015010517 | `other fall to lower level less than 6 feet` | electrocutions, electric shocks | no | **yes** | **true** |
| 2015010025 | `injured by slipping or swinging object held by injured worker` | amputations | no | no | **false** |

Rows 2015010019 and 2015010253 are the two that matter. Both have near-trivial recorded
injuries — "soreness, pain, hurt" and "cuts and abrasions" — and both are **true**: one
because a leg was pinned by powered equipment, one because a lanyard caught a fall from a
derrick. Row 2015010025 is the mirror image: `Amputations`, a permanent injury, labelled
**false**, because a hand knife has no fatality pathway. A severity-based rule gets all three
backwards.

Largest negative groups (sanity check that `false` looks like `false`):
`other fall to lower level less than 6 feet` 3,512 · `fall on same level due to slipping`
3,350 · `fall on same level due to tripping over an object` 2,553 ·
`struck against moving part of machinery or equipment` 2,232 ·
`exposure to environmental heat` 2,099 ·
`injured by slipping or swinging object held by injured worker` 2,091.

### The 66.3% is a frame statistic, not the training balance

This is **not** the class balance the classifier gets trained on. `PRD.md` asks for
2,000–3,000 records sampled from this frame; the sampling ratio is a separate, explicit
decision (Block 3 part 2), taken *after* this rule is approved.

**The rule must not be tuned to produce a prettier balance.** Bending the definition of
fatal potential to hit 50/50 is precisely the kind of thing that collapses under a judge's
question. Adjust the *sample*, never the rule.

---

## 8. Edge cases, with the decided handling

| Case | Rows | Handling |
|---|---|---|
| Duplicate `ID` | 5 | First occurrence kept, rest dropped (E2) |
| Null `EventTitle` / `NatureTitle` | 1 (`20251111222`) | Dropped (E3). Its codes are `Event 6439` / `Nature 1111`, unusable per § 4.1 |
| `NaN` in `Hospitalized` / `Amputation` / `Loss of Eye` | 8 | Irrelevant — no positive test reads these columns (§ 1.4) |
| Narrative under 20 chars | 3 | Dropped (E4) — nothing to localize |
| `EventTitle` = `nonclassifiable` | 788 | No A match by design; **79 positive via B**, 709 negative — an accepted false-negative pool (§ 9.2) |
| Sub-6-foot fall with lethal-grade injury | 4,378 sub-6ft falls | A1 excludes them, but **643 are positive via B**. A 4-foot fall ending in an intracranial bleed or an electrocution is correctly positive |
| Fall arrested by PFAS | 64 | **All 64 positive** via A3 (§ 1.3). Previously 52 were negative — the error this revision fixes |
| Amputation from a low-energy event | 6,022 | Negative. Permanent ≠ fatal pathway (§ 1.2, Test B asymmetry). Largest groups: `struck against moving part of machinery or equipment` 1,835, `injured by slipping or swinging object held by injured worker` 1,001 |
| Two or more people hospitalized | 618 in frame | **No longer a positive test** (§ 1.4). 520 are positive anyway via A or B; the remaining 98 label negative |
| Leading-space titles (2024+) | 17,863 | Handled by step 0; era gap of 0.9 points confirms it works |
| Narrative mentions a death | 8 | The rule ignores narrative text by design. Whether A/B happens to catch each was not checked; at 8 of 103,190 it moves no metric |
| Multi-hazard event | many | Irrelevant here — `sif_potential` is binary. Multi-hazard is the **IOGP tagger's** job (`PRD.md`: sigmoid multi-label) |

---

## 9. What this rule will get wrong

Stated in full, because a rule whose failure modes are unknown is not defensible.

1. **No fatality in the data means no ground truth, at all.** Precision and recall against
   real fatal potential are **unmeasurable inside this file** (§ 3). Every accuracy number
   this project ever reports measures *agreement with this rule*, never *correctness about
   fatality*. Anyone who reports it as the latter is overclaiming.

2. **`nonclassifiable` and `unspecified` codings leak into the negative class.** 709
   `nonclassifiable` rows plus a long tail of `…unspecified` titles fail test A because
   OSHA's coder never recorded the mechanism. Some were certainly high-energy. **Direction of
   error: false negatives.** B recovers only 79 of them.

3. **Test A over-triggers on the low-energy end of broad classes.** `caught in or compressed
   by equipment or objects unspecified` covers both a fatal crush and a finger nipped in a
   drawer slide; both label positive. **Direction: false positives.** Deliberate — under a
   fatal-*potential* definition, recall on the mechanism is worth more than precision on the
   observed outcome, and a near-miss classifier that misses hazards is worse than one that
   over-flags. This is a judgment call, and the one most open to challenge.

4. **The 6-foot fall cutoff is a proxy for energy, not energy.** A 5-foot fall onto a
   drill-floor valve handle can kill; a 10-foot fall into water usually does not. The band is
   used because § 4.2 leaves it as the only height distinction that survives both OIICS
   versions. B claws back 643 of the 4,378 excluded.

5. **Barrier state is mostly invisible to this rule.** § 1.3 is a real criterion but the
   structured coding surfaces it in only the two places A3 and A2's maintenance patterns
   exploit. Every event where a guard was removed, a permit skipped, or an exclusion zone
   ignored — and the code did not say so — is labelled on mechanism alone. **Direction: false
   negatives**, and the largest gap between what § 1 defines and what § 5 can measure.

6. **Heat exposure labels overwhelmingly negative.** The `exposure to environmental heat`
   family is 2,628 rows in the frame; only **163 come out positive**, leaving **2,465
   negative** — all 163 rescued by `heat stroke` in `NatureTitle` rather than by any event
   test. Heat stroke kills outdoor workers, and this dataset is being localized to Assam and
   Rajasthan, where heat is a genuine fatal hazard. Defensible on grounds that no IOGP
   Life-Saving Rule covers heat, but it is the largest single blind spot in the deployed
   context and is named here rather than hidden.

7. **U.S. injury mix ≠ Indian upstream oil-and-gas injury mix.** The frame is dominated by
   manufacturing, construction and retail. Well-control events, H₂S release, and pressurized
   hydrocarbon exposure are barely represented, so the trained classifier will be weakest on
   the hazards that matter most to the actual user. Localizing the *prose* does not fix the
   *distribution*.

8. **Removing the multi-casualty test costs real positives.** 98 rows now label negative that
   were positive before, and a few are genuine process-safety events — a machine blowing out
   hot polyphenylene sulfide onto four workers is the clearest. Accepted anyway: a rule
   that consults a hospitalization count cannot answer *"so is it SIF because two people got
   hurt?"* without conceding the definition. Paying it as a named false negative is cheaper
   than losing § 1.4.

9. **The dataset contains zero true near-misses — the single biggest gap.** Every row is a
   real hospitalization, amputation, or eye loss, because that is the reporting trigger
   (§ 3). But the PRD's headline capability is flagging a near-miss *where nobody was hurt*.
   As it stands, **the classifier will never have seen one in training.** The mitigation
   belongs to the localization step (part 2): rewrite a controlled share of test-A positives
   into near-miss framing — the load swings past the worker and strikes the deck — while
   **keeping `sif_potential = true`, since the mechanism is unchanged.** The 64 A3 rows are
   the template: mechanism intact, outcome minimal, label positive. Not built here; flagged
   as required.

10. **A substring rule fails silently when OSHA's phrasing does not match the pattern.** This
    is not hypothetical: the pattern audit for this revision found six A2 patterns that never
    fired, mislabelling 1,775 rows negative on mechanisms the rule already claimed (§ 5 A2).
    Nothing about the output looked wrong — the percentage was plausible, the era gap was
    small, the top-negative groups looked like genuine low-energy events. **The only way to
    catch this class of error is to enumerate the distinct title inventory and read the
    negatives, not to re-read the pattern list.** 2,274 vehicle-or-struck-by-worded rows
    remain negative after the repair; they were inspected and are genuinely low-energy
    (`struck by or caught in swinging door or gate` 542, `struck by door gate window` 177,
    `struck by rolling object or equipment being pushed by injured worker` 198) — but that
    conclusion has a shelf life, and any future edit to A2 needs the same audit re-run.

---

## 10. Not decided in this document

Deferred deliberately — each needs its own `DECISIONS.md` entry when taken:

- The 2,000–3,000-record sampling strategy and the target class balance (§ 7).
- `iogp_rules` multi-label assignment, `precursor_*` span extraction — different labels,
  different rules, not yet written. `precursor_barrier_failure` is where § 1.3 gets its full
  treatment (§ 9.5).
- The near-miss rewriting share and prompt (§ 9.9).
- The 15% test-split method (`PRD.md` requires the split before any training).
- Noise injection ratios (`PRD.md`: ~30% moderate / 10% heavy / 60% clean).

---

## 11. How to verify this rule by hand

A stranger with the CSV and no code should reach identical labels:

1. Open a row. Read **`EventTitle` and `NatureTitle`. Cover every other column** — in
   particular `Hospitalized`, `Amputation`, and `Loss of Eye`, which must not influence the
   answer (§ 1.4).
2. Normalize both titles per step 0 (lowercase; punctuation to spaces; collapse spaces).
3. Run E1–E4. If any hits → excluded, stop.
4. Search the normalized `EventTitle` for the A1, A2 and A3 patterns; search the normalized
   `NatureTitle` for the B patterns.
5. Any hit → `true`. No hit → `false`.

No step requires judgment, so two annotators must agree. **If they disagree, this document is
defective and gets fixed here first** — never patched downstream in a script.

### Answering a judge

*"How did you decide this report is SIF-potential?"* — the answer walks § 1, never the
injury:

> The coded mechanism is `caught in running equipment or machinery during maintenance
> cleaning`. Rotating machinery is lethal-grade energy and the worker's hands were inside it
> (§ 1.1 — credible exposure). Reaching a fatality from there needs one variable to change:
> which part of the body entered first (§ 1.2 — plausible pathway). The equipment was running
> during maintenance, so the energy-isolation barrier was absent (§ 1.3 — barrier state). The
> worker recorded "soreness, pain, hurt"; that is not part of the determination and could not
> be, because no positive test in this rule may read an outcome column (§ 1.4).

Every clause is checkable from two columns by anyone holding the file.
