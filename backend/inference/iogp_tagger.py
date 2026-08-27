"""IOGP Life-Saving Rule tagging. One public function, `tag_iogp_rules`.

THE SIGNATURE IS FROZEN (`STAGES.md` § FROZEN files):
`tag_iogp_rules(text) -> list[(rule_name, confidence)]`.

MULTI-LABEL, NOT MULTI-CLASS. `PRD.md` § ML pipeline detail specifies a 9-way **sigmoid** head:
zero, one, or several rules per report, each with an independent confidence. So the scores below
deliberately do NOT sum to 1, and returning an empty list is a correct answer - an ordinary
same-level trip maps to no rule at all. Anything that normalizes these numbers across rules has
turned the sigmoid head back into a softmax one and broken the contract.

Rule names come from the checkpoint's own `id2label`, and the loader asserts that set is exactly
`schemas.IOGP_RULE_NAMES` - the canonical 9 in `PRD.md` § Glossary. So a checkpoint trained on a
renamed or reordered label set fails loudly at load instead of writing a tenth rule name into
`iogp_tags.rule_name`.

=== WHAT THESE WEIGHTS CAN AND CANNOT DO, FROM `tagger_metrics.json` =====================
Validation macro-F1 0.168. Held-out test micro-F1 0.422, macro-F1 0.296 over only the five
rules with enough test support to score. Per-rule, on the held-out set:

  Energy Isolation      P 0.33  R 1.00  F1 0.50   - fires on nearly everything
  Line of Fire          P 0.48  R 0.61  F1 0.54   - the largest class, 85 train rows
  Working at Height     P 0.38  R 0.55  F1 0.44
  Bypassing Safety Controls  F1 0.00  - 6 test rows, none found
  Driving               F1 0.00  - 5 test rows, none found
  Safe Mechanical Lifting    F1 0.00  - 2 test rows, low support
  Confined Space / Hot Work  not computable - ZERO test rows
  Work Authorisation    UNTRAINABLE - zero train rows too, so the head has never seen a
                        positive example and cannot emit this rule meaningfully at all
                        (`AUDIT.md` 2026-08-26: no narrative in this corpus states a permit
                        failure).

Read that as: two rules are weakly usable, one over-fires, three score zero, and three cannot
be measured. It is a 277-row corpus. The numbers are logged rather than smoothed because a
demo that claims nine working rules has claimed six it does not have.
========================================================================================
"""

import json
from functools import lru_cache
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from schemas import IOGP_RULE_NAMES

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "model_weights" / "iogp_tagger"

MODEL_VERSION = "distilbert-iogp-1.0"

_METRICS = json.loads((WEIGHTS_DIR / "tagger_metrics.json").read_text(encoding="utf-8"))

# A rule is emitted at or above this sigmoid score. Independent per rule, as a sigmoid head is.
# Tuned on the validation split by `scripts/train_iogp_tagger.py` and read from its metrics file
# rather than hardcoded, so a retrain that moves it cannot leave a stale copy here.
TAG_THRESHOLD = float(_METRICS["threshold"])
MAX_LENGTH = int(_METRICS["max_length"])


@lru_cache(maxsize=1)
def _tokenizer_and_model():
    """Load once, on first call, and keep it. Same lazy-load reasoning as `sif_classifier`.

    The label-set assertion lives here rather than at module import so that a bad checkpoint
    fails on the first inference call with a readable message, instead of breaking `uvicorn`
    startup for every endpoint including the ones that never touch a model.
    """
    tokenizer = AutoTokenizer.from_pretrained(WEIGHTS_DIR)
    model = AutoModelForSequenceClassification.from_pretrained(WEIGHTS_DIR)
    model.eval()  # disables dropout; without it two identical calls can disagree

    labels = set(model.config.label2id)
    if labels != set(IOGP_RULE_NAMES):
        raise ValueError(
            f"checkpoint labels do not match schemas.IOGP_RULE_NAMES. "
            f"unexpected {sorted(labels - set(IOGP_RULE_NAMES))}, "
            f"missing {sorted(set(IOGP_RULE_NAMES) - labels)}")
    return tokenizer, model


def tag_iogp_rules(text: str) -> list[tuple[str, float]]:
    """Return [(rule_name, confidence)] for every applicable rule. Empty list is valid.

    FROZEN SIGNATURE. Confidences are independent per rule and do not sum to 1.

    Empty input returns no rules without a forward pass - there is nothing to tag, and an
    empty list is already a correct answer for text that breaks no rule.
    """
    if not text or not text.strip():
        return []

    tokenizer, model = _tokenizer_and_model()
    batch = tokenizer(text, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
    with torch.no_grad():
        logits = model(**batch).logits[0]

    # Sigmoid, never softmax: nine independent yes/no decisions. `BCEWithLogitsLoss` fused the
    # sigmoid into training, so it is applied here at prediction time and nowhere else.
    scores = torch.sigmoid(logits)

    tagged = [(model.config.id2label[index], round(float(score), 3))
              for index, score in enumerate(scores) if score >= TAG_THRESHOLD]

    # Highest confidence first: the Detail view renders these as chips left to right, and the
    # most probable rule is the one an HSE officer should read first.
    tagged.sort(key=lambda pair: -pair[1])
    return tagged
