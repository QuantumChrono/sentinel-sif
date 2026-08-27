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
These weights are barely better than a coin flip and the numbers are in `calibration.json`
next to them: validation accuracy 0.524 on n=42, confusion [[1,20],[0,21]] - it answers "SIF"
on 41 of 42 validation rows. Held-out test accuracy 0.510 on n=49. The cause is corpus size,
not a bug in this file: 235 fitting rows cannot teach DistilBERT this task.

The consequence is visible in production behaviour, so nobody should be surprised by it:
mean confidence is ~0.52, every one of the 42 validation and 49 test rows scores below
`CONFIDENCE_THRESHOLD = 0.65`, and therefore EVERY report routes to the Manual Review Queue
and the auto-publish path effectively does not exist. That is the honest failure mode and it
is the safe direction to fail in - a model this weak should not be publishing verdicts.
`AUDIT.md` 2026-08-26 carries the threshold sweep that establishes no better cut point exists.
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
