"""Sweep `CONFIDENCE_THRESHOLD` on the VALIDATION split. Block 8 exit criterion.

    backend/.venv/Scripts/python.exe scripts/tune_confidence_threshold.py

WHAT THE THRESHOLD DOES, because the sweep only makes sense against the decision it drives.
`routes/reports.py` writes `status = "processed"` when confidence >= threshold and
`"needs_review"` otherwise, and `routes/analytics.py` selects the Manual Review Queue by the
same number. So the threshold is not a model parameter - it is the cut between "the model
publishes this verdict unseen" and "a human reads it first". Raising it sends more to humans.

THE VALIDATION ROWS ARE THE TRAINER'S, NOT A NEW SPLIT. This imports
`stratified_val_split` from `train_sif_classifier` with the same seed and fraction rather than
re-deriving a split, so these are byte-identical to the rows the temperature was fit on. A
freshly-drawn "validation" split would overlap the fitting rows and every number below would
be a training metric wearing a validation metric's name.

`data/test/` IS NEVER OPENED BY THIS FILE. Grep it. Tuning a decision threshold on the held-out
set is the exact thing `STAGES.md` Block 6 forbids ("do NOT tune the threshold on test data"),
and it is worth being blunt about why: the test numbers are the only unbiased estimate left, and
a threshold chosen against them silently converts them into training numbers.

WHAT IS MEASURED AT EACH CANDIDATE. Three things a reviewer can act on:
  * auto_published  - how many of the validation rows the model would publish unseen
  * auto_accuracy   - of those, the share it got RIGHT. This is the number that matters: it is
                      the accuracy of the claims that reach a dashboard with no human check.
  * missed_sif      - true-SIF rows the model auto-published as NOT SIF. The expensive error,
                      counted on its own because a false negative here is a real hazard that
                      no human was ever shown.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from inference.sif_classifier import MODEL_VERSION, TEMPERATURE, classify_sif  # noqa: E402
from schemas import CONFIDENCE_THRESHOLD  # noqa: E402
from train_sif_classifier import SEED, VAL_FRACTION, read_jsonl, stratified_val_split  # noqa: E402

TRAIN_PATH = REPO_ROOT / "data" / "processed" / "train.jsonl"

# 0.50 is the floor: confidence is the winning class's probability, so it cannot fall below it.
# A threshold at 0.50 means "publish everything" and is included as the no-review baseline.
CANDIDATES = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90]


def scored_validation_rows():
    """(true_label, predicted_label, confidence) per validation row, from the REAL function.

    `classify_sif` is called rather than the model reloaded here, so the sweep measures exactly
    what ingest serves - temperature applied, rounding included. A local reimplementation could
    disagree with production by a rounding step and nobody would find out.
    """
    _, val_rows = stratified_val_split(read_jsonl(str(TRAIN_PATH)), VAL_FRACTION, SEED)
    scored = []
    for row in val_rows:
        predicted, confidence = classify_sif(row["raw_text"])
        scored.append((bool(row["sif_potential"]), predicted, confidence))
    return scored


def evaluate(scored, threshold):
    published = [(truth, predicted) for truth, predicted, conf in scored if conf >= threshold]
    correct = sum(1 for truth, predicted in published if truth == predicted)
    missed = sum(1 for truth, predicted in published if truth and not predicted)
    return {
        "threshold": threshold,
        "auto_published": len(published),
        "reviewed": len(scored) - len(published),
        "auto_accuracy": correct / len(published) if published else None,
        "missed_sif": missed,
    }


def main():
    scored = scored_validation_rows()
    confidences = sorted(conf for _, _, conf in scored)
    accuracy = sum(1 for truth, predicted, _ in scored if truth == predicted) / len(scored)

    print(f"model_version {MODEL_VERSION}  temperature {TEMPERATURE}")
    print(f"validation rows {len(scored)} (from data/processed/train.jsonl, seed {SEED}, "
          f"fraction {VAL_FRACTION}) - data/test/ NOT read")
    print(f"overall validation accuracy at argmax, threshold-independent: {accuracy:.4f}")
    print(f"confidence range {confidences[0]:.3f} - {confidences[-1]:.3f}, "
          f"median {confidences[len(confidences) // 2]:.3f}")

    print(f"\n{'threshold':>9} {'auto_published':>15} {'reviewed':>9} {'auto_accuracy':>14} "
          f"{'missed_sif':>11}")
    rows = [evaluate(scored, candidate) for candidate in CANDIDATES]
    for row in rows:
        shown = "n/a" if row["auto_accuracy"] is None else f"{row['auto_accuracy']:.4f}"
        marker = "  <- CONFIDENCE_THRESHOLD in schemas.py" if row["threshold"] == \
            CONFIDENCE_THRESHOLD else ""
        print(f"{row['threshold']:>9.2f} {row['auto_published']:>15} {row['reviewed']:>9} "
              f"{shown:>14} {row['missed_sif']:>11}{marker}")

    usable = [row for row in rows if row["auto_published"] > 0]
    print()
    if not usable:
        print("NO CANDIDATE PUBLISHES ANYTHING: every validation row is below even the lowest\n"
              "candidate, so the threshold is not the free variable here - the model's\n"
              "confidences are. Keep the current value; a lower one would only trade an empty\n"
              "auto-publish path for a coin-flip one.")
    else:
        best = max(usable, key=lambda row: (row["auto_accuracy"], row["auto_published"]))
        print(f"highest auto_accuracy among candidates that publish anything: "
              f"{best['threshold']:.2f} "
              f"({best['auto_accuracy']:.4f} over {best['auto_published']} rows, "
              f"{best['missed_sif']} missed SIF)")
        print("A threshold is only worth moving if the accuracy it buys is one an HSE officer\n"
              "would act on unseen. Read the table before changing the frozen constant.")


if __name__ == "__main__":
    main()
