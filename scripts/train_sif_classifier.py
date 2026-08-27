"""Fine-tune DistilBERT for binary SIF-potential classification. Run in a Kaggle T4 notebook.

RUN IT: upload the repo (or just `data/`), set the CONFIG paths below, Run All. No CLI args -
this is a notebook script, and a config block you can see is easier to trust than argparse.

WHY THERE IS NO EARLY STOPPING. The first real run shipped a model that answered "SIF" on 41 of
42 validation rows at ~0.52 confidence. The cause was not the corpus, as was first assumed and
written into `AUDIT.md` - it was this script. Two mechanisms combined:

  1. `EPOCHS = 12` with `PATIENCE = 3` on strict `val_f1 > best_f1`. A constant-positive
     predictor on a 21/42 validation split scores F1 0.6774 *exactly*. The head collapsed to
     all-positive during epoch 1, scored that 0.6774, and no later epoch could ever BEAT it -
     so `save_pretrained` wrote the epoch-1 weights, three more epochs ran, patience fired,
     and the collapsed epoch-1 checkpoint was the one that got served.
  2. `LEARNING_RATE = 2e-5` was too low to move the head off that collapsed init inside the
     four epochs it was given. Final train_loss was 0.7049 - and ln(2) = 0.6931, so the loss
     never left the value a coin flip produces.

Selecting a checkpoint on F1 is what made a collapse look like progress: F1 rewards answering
yes to everything. The fix is not a better patience rule. It is a FIXED training budget with a
linear-decay schedule that reaches lr 0 on the last step, so the final epoch is the intended
end of the fit, plus a loss floor (`TARGET_TRAIN_LOSS`) that is checked and reported rather
than assumed, and a per-epoch `val_positive_rate` so a collapse is visible while it happens.

WHAT THE SAVED CONFIDENCE MEANS. `backend/inference/sif_classifier.py` documents the frozen
contract: the float is confidence in the *returned verdict*, i.e. the predicted class's
probability, so a confident negative is (False, 0.88) and NOT (False, 0.12). This script
produces exactly that number, temperature-scaled, so the Block 8 swap needs no reinterpretation.

CALIBRATION IS A SINGLE TEMPERATURE, FIT ON VALIDATION ONLY. Temperature scaling divides the
logits by one scalar T learned on held-out validation data. It cannot change any prediction
(dividing both logits by T > 0 preserves the argmax), only how sure the model claims to be. T
is written to `calibration.json` next to the weights and must be applied at inference.

  An earlier version of this docstring justified T by asserting a small fine-tune is
  "over-confident by default, raw softmax reads 0.99 on rows it gets wrong." The measured run
  was the OPPOSITE: mean confidence 0.525, every one of 42 validation and 49 test rows below
  0.65, and the fitted T pinned to the LOW edge of the grid - the optimizer asking to SHARPEN
  probabilities that carried no signal to sharpen. Which direction T goes is an output of the
  run, not something to predict in a comment, so the grid now spans both directions and the
  edge warning fires either way.

SEPARATION IS REPORTED, NOT ASSUMED. A threshold is only meaningful if hazard rows and routine
rows get different probabilities. `report_on_split` prints mean p(sif) on true positives vs
true negatives and the gap between them, alongside the confidence range. A near-zero gap means
the threshold is sorting noise no matter what value it is set to - the failure the first run
had, and the one number that would have exposed it immediately.

THE TEST SET IS NOT TOUCHED UNTIL TRAINING IS OVER. `data/test/` is loaded exactly once, in
`main`, after training has finished and the temperature is already fitted. The temperature uses
a validation slice carved out of `data/processed/train.jsonl`. Using test for it would make
every number below a training metric wearing a test metric's name.
"""

import json
import os
import random
from collections import Counter, defaultdict

import numpy as np
import torch
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

# ---------------------------------------------------------------------------
# CONFIG - the only block you edit. Paths are relative to the notebook's cwd.
# On Kaggle with the repo added as a dataset, prefix with /kaggle/input/<name>/.
# ---------------------------------------------------------------------------
TRAIN_PATH = "data/processed/train.jsonl"
TEST_PATH = "data/test/test.jsonl"          # read ONCE, after training. Never for early stopping.
OUTPUT_DIR = "model_weights/sif_classifier"  # download this whole folder when the run finishes

MODEL_NAME = "distilbert-base-uncased"
MAX_LENGTH = 256      # train p95 is 106 tokens, max 133 - 256 truncates nothing
BATCH_SIZE = 16
LEARNING_RATE = 3e-5      # was 2e-5, which did not move the head off its collapsed init in 4 epochs
EPOCHS = 6                # FIXED. Every epoch runs; there is no early stopping - see the docstring
WARMUP_FRACTION = 0.1     # 10% of total steps, linear warmup then linear decay
VAL_FRACTION = 0.15
SEED = 20260826

# The run is only trusted if the fit actually converged. Checked and reported at the end of
# training, not assumed: the previous run kept an epoch-1 checkpoint at train_loss 0.7049,
# which is ln(2) = 0.693, i.e. a coin flip that had learned nothing.
TARGET_TRAIN_LOSS = 0.30


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def stratified_val_split(rows, val_fraction, seed):
    """Carve validation out of TRAIN, stratified on (sif_potential, noise_tier).

    Same pairing `scripts/split_dataset.py` uses for train/test, and for the same reason: a
    validation set of tidy clean-tier English reports would early-stop against a distribution
    the heavy-noise rows do not share.
    """
    strata = defaultdict(list)
    for row in rows:
        strata[(bool(row["sif_potential"]), row["noise_tier"])].append(row)

    rng = random.Random(seed)
    fit, val = [], []
    for key in sorted(strata, key=lambda k: (k[0], str(k[1]))):
        members = sorted(strata[key], key=lambda r: str(r["id"]))  # stable order before shuffle
        rng.shuffle(members)
        n_val = round(len(members) * val_fraction)
        val += members[:n_val]
        fit += members[n_val:]
    return fit, val


def encode(rows, tokenizer):
    batch = tokenizer([r["raw_text"] for r in rows], truncation=True, max_length=MAX_LENGTH,
                      padding="max_length", return_tensors="pt")
    labels = torch.tensor([int(bool(r["sif_potential"])) for r in rows])
    return TensorDataset(batch["input_ids"], batch["attention_mask"], labels)


def collect_logits(model, loader, device):
    model.eval()
    logits, labels = [], []
    with torch.no_grad():
        for input_ids, mask, label in loader:
            out = model(input_ids=input_ids.to(device), attention_mask=mask.to(device)).logits
            logits.append(out.float().cpu())
            labels.append(label)
    return torch.cat(logits), torch.cat(labels)


def train(model, fit_loader, val_loader, device):
    """Train for a FIXED number of epochs and keep the LAST checkpoint. Returns the final
    epoch's mean training loss.

    THERE IS NO EARLY STOPPING AND NO CHECKPOINT SELECTION, DELIBERATELY. Both used to be
    here and together they shipped an epoch-1 model. The mechanism, for anyone tempted to add
    them back: validation F1 was compared with a strict `val_f1 > best_f1`, and on a 21/42
    validation split a constant-positive predictor scores F1 0.6774 exactly. The model
    collapsed to all-positive in epoch 1, hit that 0.6774, and no later epoch could ever
    *beat* it - so the epoch-1 weights were written to disk, three more epochs ran, patience
    fired, and the collapsed checkpoint was what got served. F1 rewards a model that answers
    yes to everything, which makes it the wrong quantity to select a checkpoint on here.

    With a linear-decay schedule the learning rate reaches 0 at the last step, so the final
    epoch IS the intended endpoint of the fit rather than an arbitrary stop. The training
    budget is the hyperparameter; the model is whatever it produces. `val_positive_rate` is
    printed every epoch so a collapse is visible while it is happening, not inferred from a
    confusion matrix afterwards.
    """
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    total_steps = len(fit_loader) * EPOCHS
    warmup_steps = int(WARMUP_FRACTION * total_steps)
    scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)
    print(f"  {EPOCHS} fixed epochs, {total_steps} steps, {warmup_steps} warmup "
          f"({WARMUP_FRACTION:.0%}), lr {LEARNING_RATE}, no early stopping")

    train_loss = float("nan")
    for epoch in range(1, EPOCHS + 1):
        model.train()
        running = 0.0
        for input_ids, mask, labels in fit_loader:
            optimizer.zero_grad()
            out = model(input_ids=input_ids.to(device), attention_mask=mask.to(device),
                        labels=labels.to(device))
            out.loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running += out.loss.item()
        train_loss = running / len(fit_loader)

        logits, labels = collect_logits(model, val_loader, device)
        predictions = logits.argmax(dim=1).numpy()
        val_f1 = f1_score(labels.numpy(), predictions, zero_division=0)
        # The number that exposes the collapse F1 hides. 1.00 or 0.00 means one class only.
        positive_rate = float((predictions == 1).mean())
        print(f"  epoch {epoch:2d}  train_loss {train_loss:.4f}  val_f1 {val_f1:.4f}  "
              f"val_positive_rate {positive_rate:.2f}")

    model.save_pretrained(OUTPUT_DIR)
    print(f"  saved the epoch-{EPOCHS} checkpoint to {OUTPUT_DIR} "
          "(fixed schedule, no selection - see the docstring)")

    if train_loss > TARGET_TRAIN_LOSS:
        print()  # blank line: this warning must not be lost in the epoch log
        print(f"  WARNING: final train_loss {train_loss:.4f} did NOT reach "
              f"TARGET_TRAIN_LOSS {TARGET_TRAIN_LOSS}. At 0.693 = ln(2) the model is still a "
              "coin flip and has learned nothing; treat every metric below as a measurement of "
              "an unconverged fit, not of this task's difficulty. Raise EPOCHS or LEARNING_RATE "
              "and re-run before swapping these weights into backend/inference/.")
    else:
        print(f"  converged: final train_loss {train_loss:.4f} <= "
              f"TARGET_TRAIN_LOSS {TARGET_TRAIN_LOSS}")
    return train_loss


# Geometric, not linear: T is a ratio, so 0.1 -> 0.2 is a real change while 5.0 -> 5.1 is
# noise, and even spacing wastes most of its points where they cannot matter. Spans BOTH
# directions - the previous linear grid started at 0.5 and the real run pinned to that low
# edge, i.e. the optimum was outside the grid on the sharpening side and got clipped.
TEMPERATURE_GRID = np.geomspace(0.05, 10.0, 161)


def fit_temperature(logits, labels):
    """One scalar T minimizing validation NLL. Grid search - 161 evaluations on ~42 rows is
    instant, and it cannot diverge the way an unwatched LBFGS on this little data can.

    A T pinned to either END of the grid is reported, not swallowed: it means the true optimum
    lies outside the grid and got clipped. Both edges are bad news, for opposite reasons.

      HIGH edge - T that large flattens every probability toward 0.5, so
      `CONFIDENCE_THRESHOLD = 0.65` sends the ENTIRE feed to manual review and the auto-publish
      path silently stops existing.

      LOW edge - the optimizer is asking to SHARPEN, which on a healthy fit is fine, but on the
      real run it meant the logits were nearly tied on every row and no amount of sharpening
      could separate them. T came back 0.5 against a grid that started at 0.5. Temperature
      cannot manufacture signal that the fit did not learn; a low-edge pin next to a
      near-zero p(sif) separation gap means retrain, not recalibrate.
    """
    best_t, best_nll = 1.0, float("inf")
    for t in TEMPERATURE_GRID:
        nll = torch.nn.functional.cross_entropy(logits / t, labels).item()
        if nll < best_nll:
            best_t, best_nll = float(t), nll
    if best_t >= TEMPERATURE_GRID[-1] or best_t <= TEMPERATURE_GRID[0]:
        print(f"  WARNING: temperature {best_t:.3f} is pinned to the edge of the search grid "
              f"[{TEMPERATURE_GRID[0]}, {TEMPERATURE_GRID[-1]}]. The true optimum is outside it, "
              "so this model's confidences are barely separable - check the row count below "
              "CONFIDENCE_THRESHOLD before trusting the review-queue split.")
    return best_t, best_nll


def expected_calibration_error(confidences, correct, bins=10):
    """Average |confidence - accuracy| over equal-width confidence bins. 0 is perfect."""
    confidences, correct = np.asarray(confidences), np.asarray(correct, dtype=float)
    error = 0.0
    for lower in np.linspace(0.5, 1.0, bins + 1)[:-1]:
        upper = lower + 0.5 / bins
        in_bin = (confidences > lower) & (confidences <= upper)
        if in_bin.sum():
            error += in_bin.mean() * abs(correct[in_bin].mean() - confidences[in_bin].mean())
    return float(error)


def report_on_split(name, logits, labels, temperature):
    probabilities = torch.softmax(logits / temperature, dim=1).numpy()
    predictions = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    truth = labels.numpy()

    # THE SEPARATION NUMBERS. A threshold can only work if hazard rows and routine rows come
    # out with different p(sif). The first run reported accuracy, F1 and a confusion matrix and
    # none of the three said "this model gives every row the same score" - the confusion matrix
    # implied it, but only to someone already suspicious. This states it outright.
    p_sif = probabilities[:, 1]
    mean_p_on_true_sif = float(p_sif[truth == 1].mean()) if (truth == 1).any() else float("nan")
    mean_p_on_routine = float(p_sif[truth == 0].mean()) if (truth == 0).any() else float("nan")
    scores = {
        "n": len(truth),
        "mean_p_sif_on_true_sif": mean_p_on_true_sif,
        "mean_p_sif_on_routine": mean_p_on_routine,
        "separation": mean_p_on_true_sif - mean_p_on_routine,
        "predicted_positive_rate": float((predictions == 1).mean()),
        "confidence_min": float(confidence.min()),
        "confidence_max": float(confidence.max()),
        "accuracy": accuracy_score(truth, predictions),
        "precision": precision_score(truth, predictions, zero_division=0),
        "recall": recall_score(truth, predictions, zero_division=0),
        "f1": f1_score(truth, predictions, zero_division=0),
        "ece": expected_calibration_error(confidence, predictions == truth),
        "mean_confidence": float(confidence.mean()),
        "below_threshold_0.65": int((confidence < 0.65).sum()),
        "confusion": confusion_matrix(truth, predictions, labels=[0, 1]).tolist(),
    }
    print(f"\n{name}: n={scores['n']}  acc {scores['accuracy']:.4f}  P {scores['precision']:.4f}  "
          f"R {scores['recall']:.4f}  F1 {scores['f1']:.4f}  ECE {scores['ece']:.4f}")
    (tn, fp), (fn, tp) = scores["confusion"]
    print(f"  confusion  TN {tn}  FP {fp}  FN {fn}  TP {tp}   (rows = truth, cols = predicted)")
    print(f"  separation  mean p(sif) {scores['mean_p_sif_on_true_sif']:.4f} on real SIF rows vs "
          f"{scores['mean_p_sif_on_routine']:.4f} on routine rows  = GAP {scores['separation']:+.4f}")
    print(f"  confidence  range {scores['confidence_min']:.4f}-{scores['confidence_max']:.4f}, "
          f"mean {scores['mean_confidence']:.4f}; predicts SIF on "
          f"{100 * scores['predicted_positive_rate']:.0f}% of rows")
    if abs(scores["separation"]) < 0.05:
        print("  WARNING: separation under 0.05 - this model scores hazards and routine work "
              "almost identically, so NO threshold value sorts them. Do not tune the threshold "
              "against this; retrain.")
    return scores


def main():
    set_seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_train = read_jsonl(TRAIN_PATH)
    fit_rows, val_rows = stratified_val_split(all_train, VAL_FRACTION, SEED)
    balance = Counter(bool(r["sif_potential"]) for r in all_train)
    print(f"train file {len(all_train)} rows -> fit {len(fit_rows)} / val {len(val_rows)}  (device {device})")
    positive_share = 100 * balance[True] / len(all_train)
    print(f"CLASS BALANCE (train file): {balance[True]} true / {balance[False]} false "
          f"= {positive_share:.1f}% positive")
    # Measured, not quoted. An earlier version printed a hardcoded "50.2/49.8" here, which would
    # have kept printing that after any top-up changed the corpus underneath it.
    if 45.0 <= positive_share <= 55.0:
        print(f"IMBALANCE HANDLING: none, deliberately. The split is {positive_share:.1f}/"
              f"{100 - positive_share:.1f}, so class weights or resampling would only add a knob "
              "with nothing to correct.")
    else:
        print(f"IMBALANCE HANDLING: none applied, and at {positive_share:.1f}% positive that is "
              "now a REAL skew rather than a rounding difference. This script was written for a "
              "balanced corpus; read the confusion matrix below before trusting accuracy, and "
              "add a class weight deliberately if the minority-class recall is the number that "
              "matters.")

    fit_ids = {str(r["id"]) for r in fit_rows}
    assert not (fit_ids & {str(r["id"]) for r in val_rows}), "fit/val overlap"
    assert len(fit_rows) + len(val_rows) == len(all_train), "rows lost in the split"

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    fit_loader = DataLoader(encode(fit_rows, tokenizer), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(encode(val_rows, tokenizer), batch_size=BATCH_SIZE)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=2, id2label={0: "not_sif", 1: "sif"}).to(device)
    final_train_loss = train(model, fit_loader, val_loader, device)

    # Reload from disk rather than keeping the in-memory model: it proves the checkpoint that
    # `backend/inference/` will actually load is the one these metrics describe.
    model = AutoModelForSequenceClassification.from_pretrained(OUTPUT_DIR).to(device)
    tokenizer.save_pretrained(OUTPUT_DIR)

    val_logits, val_labels = collect_logits(model, val_loader, device)
    temperature, _ = fit_temperature(val_logits, val_labels)
    print(f"\ncalibration: T = {temperature:.3f} (fit on {len(val_rows)} validation rows only)")
    report_on_split("VALIDATION uncalibrated", val_logits, val_labels, 1.0)
    val_scores = report_on_split("VALIDATION calibrated  ", val_logits, val_labels, temperature)

    test_rows = read_jsonl(TEST_PATH)  # first and only read of data/test/
    assert not (fit_ids & {str(r["id"]) for r in test_rows}), "TEST LEAKED INTO TRAINING"
    test_loader = DataLoader(encode(test_rows, tokenizer), batch_size=BATCH_SIZE)
    test_logits, test_labels = collect_logits(model, test_loader, device)
    test_scores = report_on_split("HELD-OUT TEST calibrated", test_logits, test_labels, temperature)

    with open(os.path.join(OUTPUT_DIR, "calibration.json"), "w", encoding="utf-8") as handle:
        # The training hyperparameters travel WITH the weights. `calibration.json` is already
        # read at inference, and the previous run's file recorded only T - so nothing next to
        # the weights said they came from an unconverged epoch-1 fit.
        json.dump({"temperature": temperature, "max_length": MAX_LENGTH, "seed": SEED,
                   "fit_rows": len(fit_rows), "val_rows": len(val_rows),
                   "epochs": EPOCHS, "learning_rate": LEARNING_RATE,
                   "warmup_fraction": WARMUP_FRACTION,
                   "final_train_loss": final_train_loss,
                   "converged": bool(final_train_loss <= TARGET_TRAIN_LOSS),
                   "early_stopping": False,
                   "val": val_scores, "test": test_scores}, handle, indent=2)

    (tn, fp), (fn, tp) = test_scores["confusion"]
    # Severity is COMPUTED, not typed in. The previous version hardcoded "low" and printed it
    # under an all-positive coin-flip model, which is how a broken run got filed as a routine
    # metric. A run that did not converge, or that cannot separate the classes, is a high.
    converged = final_train_loss <= TARGET_TRAIN_LOSS
    separated = abs(test_scores["separation"]) >= 0.05
    severity = "low" if (converged and separated) else "high"
    verdict = ("converged and the classes separate - these weights are usable"
               if converged and separated else
               "NOT USABLE: " + "; ".join(
                   ([] if converged else
                    [f"train_loss {final_train_loss:.4f} never reached {TARGET_TRAIN_LOSS}"])
                   + ([] if separated else
                      [f"p(sif) separation only {test_scores['separation']:+.4f}"])))
    print(f"""
================ PASTE INTO AUDIT.md ================
Type: metric | Severity: {severity}
SIF classifier ({MODEL_NAME}, seed {SEED}): trained on {len(fit_rows)} rows from
data/processed/train.jsonl with {len(val_rows)} held back for temperature fitting only -
there is NO early stopping and no checkpoint selection, the epoch-{EPOCHS} weights are what
ships. data/test/ read once, after training. {EPOCHS} epochs, lr {LEARNING_RATE},
{WARMUP_FRACTION:.0%} warmup, final train_loss {final_train_loss:.4f} against a
TARGET_TRAIN_LOSS of {TARGET_TRAIN_LOSS} -> {verdict}. Train-file class balance
{balance[True]} true / {balance[False]} false ({100 * balance[True] / len(all_train):.1f}% positive) - no class
weighting applied, the split needs none. HELD-OUT TEST (n={test_scores['n']}):
accuracy {test_scores['accuracy']:.4f}, precision {test_scores['precision']:.4f},
recall {test_scores['recall']:.4f}, F1 {test_scores['f1']:.4f}. Confusion matrix
TN {tn} / FP {fp} / FN {fn} / TP {tp}. Predicts SIF on
{100 * test_scores['predicted_positive_rate']:.0f}% of test rows (a rate near 100% or 0% is a
collapsed classifier, whatever the F1 says). SEPARATION: mean p(sif)
{test_scores['mean_p_sif_on_true_sif']:.4f} on real SIF rows vs
{test_scores['mean_p_sif_on_routine']:.4f} on routine rows, gap
{test_scores['separation']:+.4f}. Calibration temperature {temperature:.3f} fit on validation:
test ECE {test_scores['ece']:.4f}, mean confidence {test_scores['mean_confidence']:.4f},
confidence range {test_scores['confidence_min']:.4f}-{test_scores['confidence_max']:.4f},
{test_scores['below_threshold_0.65']} of {test_scores['n']} test rows below CONFIDENCE_THRESHOLD 0.65
(those route to the review queue). Validation F1 {val_scores['f1']:.4f}, validation ECE
{val_scores['ece']:.4f}, validation separation {val_scores['separation']:+.4f}.
Weights + tokenizer + calibration.json in {OUTPUT_DIR}.
=====================================================""")


if __name__ == "__main__":
    main()
