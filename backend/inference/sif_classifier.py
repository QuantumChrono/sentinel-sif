"""SIF-potential classification. One public function, `classify_sif`.

THE SIGNATURE IS FROZEN (`STAGES.md` § FROZEN files): `classify_sif(text) -> (bool, float)`.

WHAT THE FLOAT MEANS. It is the confidence in the *returned verdict* - the predicted class's
probability, which is exactly what a softmax head gives you. So a confident negative is
`(False, 0.88)`, not `(False, 0.12)`. `routes/reports.py` compares it against
`CONFIDENCE_THRESHOLD` without caring which class won.

THE TEMPERATURE IS NOT OPTIONAL. `calibration.json` carries one scalar T fit on the validation
split by `scripts/train_sif_classifier.py`. Dividing both logits by T cannot change the argmax,
only how sure the model claims to be, and the threshold comparison is meaningless without it.
It is read from the file rather than hardcoded so a retrain cannot silently invalidate it.

=== READ THIS BEFORE TRUSTING A VERDICT FROM THIS FILE ==================================
These weights are weak but no longer degenerate. Every number below is read from
`calibration.json` in this directory, which the training script writes from computed values.

  HELD-OUT TEST (n=49, the only honest number): accuracy 0.5918, precision/recall/F1 0.5833,
  mean p(sif) 0.5723 on true-SIF rows vs 0.4598 on routine - a separation of just +0.1126.
  VALIDATION (n=42): accuracy 0.6905, confusion [[15,6],[7,14]], separation +0.2662.

Read those two lines together, because the gap between them IS the finding: test separation is
less than half validation separation, which is overfitting on 235 fitting rows. Test accuracy
0.5918 is a weak model - better than the coin flip it used to be, not a good classifier.

WHAT THIS MEANS FOR THE REVIEW QUEUE. Confidences span 0.519-0.874 on test with a mean of
0.7296, and 12 of 49 test rows fall below `CONFIDENCE_THRESHOLD = 0.65`. So the threshold is a
real cut point that routes roughly a quarter of reports to a human, and the auto-publish path
genuinely exists - it did not with the earlier epoch-1 checkpoint, whose whole test set scored
below 0.65 and whose sweep in `AUDIT.md` 2026-08-27 therefore found no usable cut point. That
sweep's conclusion does not describe these weights; do not quote it against them.

The temperature below (T = 1.201) is fit on validation, not the identity, so these confidences
are scaled - `ece` in `calibration.json` is 0.1446 on validation and 0.1786 on test, meaning
the model is still measurably over-confident even after scaling.
========================================================================================
"""

import json
from functools import lru_cache
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "model_weights" / "sif_classifier"

# Written into `classifications.model_version` on every row, so a query can always separate
# these rows from the interim-keyword rows that preceded them:
#   select count(*) from classifications where model_version = 'interim-keyword-0.1';
MODEL_VERSION = "distilbert-sif-1.0"

# Fit on validation only, by the training script. Read, never assumed - a retrain rewrites it.
_CALIBRATION = json.loads((WEIGHTS_DIR / "calibration.json").read_text(encoding="utf-8"))
TEMPERATURE = float(_CALIBRATION["temperature"])
MAX_LENGTH = int(_CALIBRATION["max_length"])


@lru_cache(maxsize=1)
def _tokenizer_and_model():
    """Load once, on first call, and keep it. `lru_cache` rather than two module globals: it is
    stdlib, it is one line, and it makes the load lazy so importing this module stays cheap.

    Lazy means the FIRST request after a cold start pays the load (measured at ~1.4 s locally,
    `AUDIT.md`). On Render's free tier, which spins down when idle, that lands on top of the
    container wake - wake the backend before a demo rather than at it (`STAGES.md` § DEPLOYED).
    """
    tokenizer = AutoTokenizer.from_pretrained(WEIGHTS_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(WEIGHTS_DIR)
    model.eval()  # disables dropout; without it two identical calls can disagree
    return tokenizer, model


def classify_sif(text: str) -> tuple[bool, float]:
    """Return (sif_potential, confidence_in_that_verdict).

    FROZEN SIGNATURE. Confidence is the predicted class's probability, so it is high for a
    confident negative too - see the module docstring.

    Empty input is answered without a forward pass. `schemas.ReportCreate` rejects it long
    before ingest reaches here, but this function is also called directly by the scripts in
    `scripts/`, and DistilBERT on a zero-token sequence is a wasted 40 ms to reach the same
    "no evidence either way" answer. 0.5 is below every plausible threshold, so it routes to
    a human, which is the correct destination for a report with no text in it.
    """
    if not text or not text.strip():
        return False, 0.5

    tokenizer, model = _tokenizer_and_model()
    batch = tokenizer(text, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    with torch.no_grad():
        logits = model(**batch).logits

    probabilities = torch.softmax(logits / TEMPERATURE, dim=1)[0]
    predicted = int(probabilities.argmax())
    # `id2label` is read rather than assumed: label 1 is "sif" in this checkpoint's config, and
    # trusting index order instead would invert every verdict if a retrain ever swapped them.
    sif_potential = model.config.id2label[predicted] == "sif"
    return sif_potential, round(float(probabilities[predicted]), 3)
