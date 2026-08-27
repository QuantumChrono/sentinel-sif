"""Fine-tune DistilBERT as a 9-way MULTI-LABEL IOGP rule tagger. Run in a Kaggle T4 notebook.

RUN IT: upload the repo (or just `data/`), set the CONFIG paths below, Run All. No CLI args.

=============================================================================
WHY SIGMOID + BCEWithLogitsLoss, AND WHY SOFTMAX + CROSS-ENTROPY WOULD BE A BUG
=============================================================================
Softmax makes the 9 outputs compete: it forces them to sum to 1, so the model can only answer
"WHICH ONE of the nine rules is this?" That question is wrong for this data three ways, and the
training file proves each one with a count:

  * 40 of 277 rows carry TWO rules and 2 carry THREE - one incident breaks several rules at
    once (a crane load dropped from height is Safe Mechanical Lifting AND Line of Fire AND
    Working at Height). Softmax cannot express that; raising one rule's probability must lower
    another's, so a genuinely multi-rule report can only be scored as a hedge between rules.
  * 119 of 277 rows carry ZERO rules - an ordinary same-level slip breaks no life-saving rule.
    Softmax has no way to say "none": its outputs sum to 1, so it must always name a winner.
    An empty list is a correct and common answer here (`backend/inference/iogp_tagger.py`
    documents the same contract), and only independent per-rule scores can produce one.
  * Cross-entropy takes a single integer class index as its target. Our target is a 9-length
    0/1 vector. There is no integer to hand it.

Sigmoid squashes each of the 9 logits independently to its own 0-1 probability, and
BCEWithLogitsLoss scores each of the 9 as its own separate yes/no question. Nine independent
decisions, which is exactly the labelling schema. The scores deliberately do NOT sum to 1;
anything that normalizes them across rules has turned this back into a softmax head and broken
the contract the frontend and the interim tagger were both written against.

(BCEWithLogitsLoss, not Sigmoid followed by BCELoss: it fuses the sigmoid into the loss with a
log-sum-exp trick, so a saturated logit gives a finite gradient instead of a NaN. It therefore
takes RAW LOGITS - applying sigmoid before it would apply sigmoid twice and quietly cripple
training. Sigmoid is applied only at prediction time, in `predict_probabilities`.)

THE TEST SET IS NOT TOUCHED UNTIL TRAINING AND THRESHOLD TUNING ARE BOTH OVER. `data/test/` is
read once, in `main`, after the checkpoint and the threshold are already fixed against a
validation slice carved out of `data/processed/train.jsonl`.

THREE OF THE NINE RULES CANNOT BE HONESTLY SCORED, AND ONE CANNOT BE TRAINED AT ALL. Measured
support, not estimates - the script re-derives and prints these, and refuses to print an F1 for
a rule with zero test examples, because an F1 over zero support is undefined, not zero. See
`AUDIT.md` 2026-08-26 and the metrics block at the end of a run.
"""

import json
import os
import random
from collections import Counter, defaultdict

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, TensorDataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

# ---------------------------------------------------------------------------
# CONFIG - the only block you edit. Paths are relative to the notebook's cwd.
# On Kaggle with the repo added as a dataset, prefix with /kaggle/input/<name>/.
# ---------------------------------------------------------------------------
TRAIN_PATH = "data/processed/train.jsonl"
TEST_PATH = "data/test/test.jsonl"      # read ONCE, after training AND threshold tuning.
OUTPUT_DIR = "model_weights/iogp_tagger"  # download this whole folder when the run finishes

MODEL_NAME = "distilbert-base-uncased"
MAX_LENGTH = 256      # train p95 is 79 words / 433 chars, max 97 words - truncates nothing
BATCH_SIZE = 16
LEARNING_RATE = 3e-5  # a touch higher than the binary head: 9 sparse labels, weaker gradient each
EPOCHS = 15
PATIENCE = 4          # epochs without validation macro-F1 improvement before stopping
VAL_FRACTION = 0.15
SEED = 20260826

# BCE pos_weight multiplies the loss on POSITIVE examples of a label, per label, to stop the
# rare rules being learned as "always no". Uncapped it is n_negative/n_positive, which for
# Confined Space (4 of 277) is 68x - at that weight the model spams the rule to dodge one
# expensive false negative, trading a useless recall gain for precision the demo would show.
# Capped at 10x it still lifts the rare rules without that collapse.
# ponytail: one global cap, not a per-rule tuned weight. Per-rule tuning needs per-rule
# validation positives to tune against, and the rare rules have none.
POS_WEIGHT_CAP = 10.0

# `PRD.md` section Glossary, canonical 9, in PRD order - identical to `schemas.IOGP_RULE_NAMES`
# and `split_dataset.IOGP_RULES`. Listed here so a rule with ZERO examples occupies an output
# unit and prints as 0 support, rather than being invisible by absence.
IOGP_RULES = [
    "Bypassing Safety Controls", "Confined Space", "Driving", "Energy Isolation",
    "Hot Work", "Line of Fire", "Safe Mechanical Lifting", "Work Authorisation",
    "Working at Height",
]

# A rule needs at least this many test examples before a per-rule F1 is worth printing as a
# number. Below it the metric moves in steps larger than any improvement it could measure:
# at support 2, one row is 50 points of recall.
MIN_SUPPORT_TO_REPORT = 3


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def label_vector(row):
    """Row -> 9-length multi-hot float vector. All-zeros is valid and common (119 of 277)."""
    tags = set(row.get("iogp_rules") or [])
    unknown = tags - set(IOGP_RULES)
    assert not unknown, f"row {row['id']} carries non-canonical rule(s): {sorted(unknown)}"
    return [1.0 if rule in tags else 0.0 for rule in IOGP_RULES]


def rarest_rule_stratum(row, rule_counts):
    """Stratum key for the validation split: the row's RAREST rule, or "none" if it has none.

    Splitting multi-label data at random can drop every example of a 4-example rule into one
    side. Keying on the rarest present rule makes each scarce rule divide proportionally, and
    keeps the 119 no-rule rows - which are the model's only evidence that "no rule" is an
    answer - proportional too. Not full iterative stratification; that needs a dependency to
    do properly, and the failure it prevents beyond this one is not a failure this data has.
    """
    tags = row.get("iogp_rules") or []
    return min(tags, key=lambda rule: rule_counts[rule]) if tags else "none"


def stratified_val_split(rows, val_fraction, seed):
    rule_counts = Counter(rule for row in rows for rule in (row.get("iogp_rules") or []))
    strata = defaultdict(list)
    for row in rows:
        strata[rarest_rule_stratum(row, rule_counts)].append(row)

    rng = random.Random(seed)
    fit, val = [], []
    for key in sorted(strata):
        members = sorted(strata[key], key=lambda r: str(r["id"]))  # stable order before shuffle
        rng.shuffle(members)
        n_val = round(len(members) * val_fraction)
        val += members[:n_val]
        fit += members[n_val:]
    return fit, val


def encode(rows, tokenizer):
    batch = tokenizer([r["raw_text"] for r in rows], truncation=True, max_length=MAX_LENGTH,
                      padding="max_length", return_tensors="pt")
    labels = torch.tensor([label_vector(r) for r in rows], dtype=torch.float)
    return TensorDataset(batch["input_ids"], batch["attention_mask"], labels)


def positive_weights(rows):
    """Per-rule n_negative/n_positive, capped. 1.0 for a rule with no positives at all - there
    is no positive term in its loss to weight, so the value is arbitrary and must not be inf."""
    counts = Counter(rule for row in rows for rule in (row.get("iogp_rules") or []))
    weights = []
    for rule in IOGP_RULES:
        n_pos = counts[rule]
        weights.append(1.0 if n_pos == 0 else min(POS_WEIGHT_CAP, (len(rows) - n_pos) / n_pos))
    return torch.tensor(weights, dtype=torch.float)


def predict_probabilities(model, loader, device):
    """Sigmoid, applied here and ONLY here - the loss took raw logits."""
    model.eval()
    logits, labels = [], []
    with torch.no_grad():
        for input_ids, mask, label in loader:
            out = model(input_ids=input_ids.to(device), attention_mask=mask.to(device)).logits
            logits.append(out.float().cpu())
            labels.append(label)
    return torch.sigmoid(torch.cat(logits)).numpy(), torch.cat(labels).numpy()


def measurable_macro_f1(truth, predicted, min_support=1):
    """Macro-F1 over ONLY the rules that have at least `min_support` true examples.

    sklearn's `average="macro"` with `zero_division=0` would fold every zero-support rule in as
    a 0.0 and report the mean of 9. That number is not a macro-F1 of this model, it is a
    macro-F1 of this model plus three undefined slots scored as failures - fabrication by
    averaging. So the covered rules are returned alongside the score, and every caller prints
    which ones they were.
    """
    support = truth.sum(axis=0)
    covered = [i for i in range(len(IOGP_RULES)) if support[i] >= min_support]
    if not covered:
        return 0.0, []
    scores = [f1_score(truth[:, i], predicted[:, i], zero_division=0) for i in covered]
    return float(np.mean(scores)), covered


def train(model, fit_loader, val_loader, criterion, device):
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    total_steps = len(fit_loader) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(optimizer, int(0.1 * total_steps), total_steps)

    best_f1, best_epoch, stale = -1.0, 0, 0
    for epoch in range(1, EPOCHS + 1):
        model.train()
        running = 0.0
        for input_ids, mask, labels in fit_loader:
            optimizer.zero_grad()
            # Raw logits into the loss. BCEWithLogitsLoss applies the sigmoid internally.
            logits = model(input_ids=input_ids.to(device), attention_mask=mask.to(device)).logits
            loss = criterion(logits, labels.to(device))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            running += loss.item()

        probabilities, truth = predict_probabilities(model, val_loader, device)
        val_f1, _ = measurable_macro_f1(truth, (probabilities >= 0.5).astype(int))
        print(f"  epoch {epoch:2d}  train_loss {running / len(fit_loader):.4f}  "
              f"val_macro_f1@0.5 {val_f1:.4f}")

        if val_f1 > best_f1:
            best_f1, best_epoch, stale = val_f1, epoch, 0
            model.save_pretrained(OUTPUT_DIR)
        else:
            stale += 1
            if stale >= PATIENCE:
                print(f"  early stop: no val macro-F1 improvement in {PATIENCE} epochs")
                break
    print(f"  best epoch {best_epoch}, val macro-F1 {best_f1:.4f} - saved to {OUTPUT_DIR}")


def tune_threshold(probabilities, truth):
    """One global threshold, chosen on VALIDATION for best macro-F1 over its supported rules.

    One knob, not nine: a per-rule threshold needs per-rule validation positives to fit
    against, and the rare rules have at most one. `pos_weight` also means the outputs are
    deliberately not calibrated probabilities, so 0.5 carries no special meaning and is only
    the starting point.
    """
    best_threshold, best_f1 = 0.5, -1.0
    for threshold in np.arange(0.05, 0.96, 0.05):
        f1, _ = measurable_macro_f1(truth, (probabilities >= threshold).astype(int))
        if f1 > best_f1:
            best_threshold, best_f1 = float(threshold), f1
    return best_threshold, best_f1


def per_rule_table(truth, predicted, train_support):
    """Per-rule P/R/F1, printed as "not computable" where test support is zero."""
    rows = []
    print(f"\n  {'rule':<26} {'train':>5} {'test':>4} {'TP':>3} {'FP':>3} {'FN':>3} "
          f"{'P':>7} {'R':>7} {'F1':>7}")
    for i, rule in enumerate(IOGP_RULES):
        true_column, predicted_column = truth[:, i], predicted[:, i]
        tp = int((true_column * predicted_column).sum())
        fp = int(((1 - true_column) * predicted_column).sum())
        fn = int((true_column * (1 - predicted_column)).sum())
        support = int(true_column.sum())
        entry = {"rule": rule, "train_support": train_support[rule], "test_support": support,
                 "tp": tp, "fp": fp, "fn": fn}
        if support == 0:
            entry["status"] = "not computable - zero test support"
            print(f"  {rule:<26} {train_support[rule]:>5} {support:>4} {tp:>3} {fp:>3} {fn:>3} "
                  f"{'  -  ':>7} {'  -  ':>7} {'  -  ':>7}   <- undefined, not zero")
        else:
            entry.update({
                "precision": tp / (tp + fp) if tp + fp else 0.0,
                "recall": tp / (tp + fn) if tp + fn else 0.0,
                "f1": f1_score(true_column, predicted_column, zero_division=0),
                "status": "reported" if support >= MIN_SUPPORT_TO_REPORT else "low support",
            })
            flag = "" if support >= MIN_SUPPORT_TO_REPORT else f"   <- support {support}, unreliable"
            print(f"  {rule:<26} {train_support[rule]:>5} {support:>4} {tp:>3} {fp:>3} {fn:>3} "
                  f"{entry['precision']:>7.4f} {entry['recall']:>7.4f} {entry['f1']:>7.4f}{flag}")
        rows.append(entry)
    return rows


def main():
    set_seed(SEED)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    all_train = read_jsonl(TRAIN_PATH)
    fit_rows, val_rows = stratified_val_split(all_train, VAL_FRACTION, SEED)
    train_support = Counter({rule: 0 for rule in IOGP_RULES})
    train_support.update(rule for row in all_train for rule in (row.get("iogp_rules") or []))
    cardinality = Counter(len(row.get("iogp_rules") or []) for row in all_train)

    print(f"train file {len(all_train)} rows -> fit {len(fit_rows)} / val {len(val_rows)}  (device {device})")
    print("RULES PER ROW: " + ", ".join(f"{n} rules: {cardinality[n]}" for n in sorted(cardinality)))
    print("LABEL BALANCE (train file, per rule):")
    for rule in IOGP_RULES:
        n = train_support[rule]
        print(f"  {rule:<26} {n:>4} / {len(all_train)}  ({100 * n / len(all_train):>5.1f}% positive)")
    # Counted, not quoted. An earlier version hardcoded "4 Confined Space rows" and printed it
    # unchanged against a corpus that held 2, contradicting the table directly above it.
    rarest_rule, rarest_count = min(
        ((rule, train_support[rule]) for rule in IOGP_RULES if train_support[rule] > 0),
        key=lambda pair: pair[1], default=("(no rule has any example)", 0))
    rows_word = "row" if rarest_count == 1 else "rows"
    print("IMBALANCE HANDLING: BCE pos_weight = n_neg/n_pos per rule, capped at "
          f"{POS_WEIGHT_CAP}x (see the POS_WEIGHT_CAP comment). No resampling: duplicating the "
          f"{rarest_count} {rarest_rule} {rows_word} would teach those {rarest_count} "
          f"{'sentence' if rarest_count == 1 else 'sentences'}, not the rule.")

    untrainable = [rule for rule in IOGP_RULES if train_support[rule] == 0]
    if untrainable:
        print(f"\n  *** UNTRAINABLE: {untrainable} - zero positive examples in the training "
              "file. Those output units can only ever learn to predict 0. They are kept so the "
              "head stays 9-wide and the rule indices match IOGP_RULE_NAMES, but the model has "
              "learned NOTHING about them and must not be described as covering all 9 rules.")

    fit_ids = {str(r["id"]) for r in fit_rows}
    assert not (fit_ids & {str(r["id"]) for r in val_rows}), "fit/val overlap"
    assert len(fit_rows) + len(val_rows) == len(all_train), "rows lost in the split"

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    fit_loader = DataLoader(encode(fit_rows, tokenizer), batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(encode(val_rows, tokenizer), batch_size=BATCH_SIZE)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(IOGP_RULES), problem_type="multi_label_classification",
        id2label={i: rule for i, rule in enumerate(IOGP_RULES)},
        label2id={rule: i for i, rule in enumerate(IOGP_RULES)}).to(device)
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=positive_weights(fit_rows).to(device))
    train(model, fit_loader, val_loader, criterion, device)

    model = AutoModelForSequenceClassification.from_pretrained(OUTPUT_DIR).to(device)
    tokenizer.save_pretrained(OUTPUT_DIR)

    val_probabilities, val_truth = predict_probabilities(model, val_loader, device)
    threshold, val_f1 = tune_threshold(val_probabilities, val_truth)
    print(f"\nthreshold {threshold:.2f}, chosen on {len(val_rows)} VALIDATION rows only "
          f"(val macro-F1 {val_f1:.4f}; 0.50 would give "
          f"{measurable_macro_f1(val_truth, (val_probabilities >= 0.5).astype(int))[0]:.4f})")

    test_rows = read_jsonl(TEST_PATH)  # first and only read of data/test/
    assert not (fit_ids & {str(r["id"]) for r in test_rows}), "TEST LEAKED INTO TRAINING"
    test_loader = DataLoader(encode(test_rows, tokenizer), batch_size=BATCH_SIZE)
    test_probabilities, test_truth = predict_probabilities(model, test_loader, device)
    test_predicted = (test_probabilities >= threshold).astype(int)

    print(f"\nHELD-OUT TEST (n={len(test_rows)}, threshold {threshold:.2f})")
    table = per_rule_table(test_truth, test_predicted, train_support)
    macro_f1, covered = measurable_macro_f1(test_truth, test_predicted, MIN_SUPPORT_TO_REPORT)
    reportable, low, absent = ([r["rule"] for r in table if r["status"] == "reported"],
                               [r["rule"] for r in table if r["status"] == "low support"],
                               [r["rule"] for r in table if r["test_support"] == 0])
    micro_f1 = f1_score(test_truth.ravel(), test_predicted.ravel(), zero_division=0)
    empty_rows = test_truth.sum(axis=1) == 0
    empty_correct = int((test_predicted[empty_rows].sum(axis=1) == 0).sum())

    print(f"\n  MACRO-F1 {macro_f1:.4f} over the {len(covered)} rules with test support "
          f">= {MIN_SUPPORT_TO_REPORT}: {reportable}")
    print(f"  micro-F1 {micro_f1:.4f} (all 9 x {len(test_rows)} rule decisions pooled)")
    print(f"  empty-list rows: {empty_correct}/{int(empty_rows.sum())} of the no-rule test rows "
          "were correctly tagged with nothing")
    if low:
        print(f"  LOW SUPPORT, excluded from macro-F1, printed above but unreliable: {low}")
    if absent:
        print(f"  NOT MEASURABLE AT ALL, zero test examples: {absent}")

    with open(os.path.join(OUTPUT_DIR, "tagger_metrics.json"), "w", encoding="utf-8") as handle:
        json.dump({"threshold": threshold, "max_length": MAX_LENGTH, "seed": SEED,
                   "pos_weight_cap": POS_WEIGHT_CAP, "rules": IOGP_RULES,
                   "val_macro_f1": val_f1, "test_macro_f1_measurable": macro_f1,
                   "test_micro_f1": micro_f1, "macro_f1_covers": reportable,
                   "low_support": low, "not_measurable": absent,
                   "untrainable": untrainable, "per_rule": table}, handle, indent=2)

    lines = "\n".join(
        f"  {r['rule']}: train {r['train_support']}, test {r['test_support']} - " +
        (r["status"] if "f1" not in r else
         f"P {r['precision']:.4f} R {r['recall']:.4f} F1 {r['f1']:.4f}"
         f"{' (LOW SUPPORT, unreliable)' if r['status'] == 'low support' else ''}")
        for r in table)
    print(f"""
================ PASTE INTO AUDIT.md ================
Type: metric | Severity: med
IOGP tagger ({MODEL_NAME}, 9-way sigmoid multi-label head, BCEWithLogitsLoss, seed {SEED}):
trained on {len(fit_rows)} rows from data/processed/train.jsonl with {len(val_rows)} held back for
early stopping and threshold selection; data/test/ read only afterwards. Tag threshold
{threshold:.2f}, tuned on validation (val macro-F1 {val_f1:.4f}). pos_weight = n_neg/n_pos per rule
capped at {POS_WEIGHT_CAP}x. Per-rule on the HELD-OUT TEST (n={len(test_rows)}):
{lines}
MACRO-F1 {macro_f1:.4f}, computed over the {len(covered)} rules with test support >= {MIN_SUPPORT_TO_REPORT}
({reportable}) and NOT over all 9 - an F1 over zero support is undefined, not zero.
micro-F1 {micro_f1:.4f}. {empty_correct}/{int(empty_rows.sum())} no-rule test rows correctly tagged with nothing.
Unmeasurable, zero test examples: {absent}. Untrainable, zero TRAIN examples: {untrainable}.
Do not describe this model as covering all 9 rules. Weights + tokenizer + tagger_metrics.json
in {OUTPUT_DIR}.
=====================================================""")


if __name__ == "__main__":
    main()
