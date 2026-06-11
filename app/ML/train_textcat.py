"""
Train a spaCy textcat component on labeled email data exported from the DB.

Prerequisites:
    1. poetry run python -m app.ML.export_training_data
       → creates app/ML/data/train.spacy + dev.spacy

Usage:
    cd irisBackend
    poetry run python -m app.ML.train_textcat

Output: app/ML/models/iris_textcat/   (spaCy model directory)

The trained model is loaded at runtime by app/nlp/textcat_classifier.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = Path(__file__).parent / "configs" / "textcat.cfg"
OUTPUT_DIR = Path(__file__).parent / "models" / "iris_textcat"
TRAIN_PATH = Path(__file__).parent / "data" / "train.spacy"
DEV_PATH = Path(__file__).parent / "data" / "dev.spacy"

LABELS = ["rdv", "action", "attente", "bonsplans", "info"]


def _check_prerequisites() -> bool:
    ok = True
    if not TRAIN_PATH.exists():
        print(f"[ERROR] Training data not found: {TRAIN_PATH}", file=sys.stderr)
        print("       Run: poetry run python -m app.ML.export_training_data", file=sys.stderr)
        ok = False
    if not DEV_PATH.exists():
        print(f"[ERROR] Dev data not found: {DEV_PATH}", file=sys.stderr)
        ok = False
    return ok


def _count_examples(path: Path) -> dict[str, int]:
    import spacy
    from spacy.tokens import DocBin

    nlp = spacy.blank("fr")
    db = DocBin().from_disk(path)
    counts: dict[str, int] = {lbl: 0 for lbl in LABELS}
    for doc in db.get_docs(nlp.vocab):
        for lbl, score in doc.cats.items():
            if score > 0.5:
                counts[lbl] = counts.get(lbl, 0) + 1
    return counts


def train() -> None:
    import spacy
    from spacy.cli.train import train as spacy_train

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Iris textcat trainer")
    print("=" * 50)
    print(f"Config:    {CONFIG_PATH}")
    print(f"Output:    {OUTPUT_DIR}")
    print()

    # Show data stats before training
    print("Training data distribution:")
    for lbl, count in sorted(_count_examples(TRAIN_PATH).items()):
        print(f"  {lbl:<12} {count:>4} examples")
    print()
    print("Dev data distribution:")
    for lbl, count in sorted(_count_examples(DEV_PATH).items()):
        print(f"  {lbl:<12} {count:>4} examples")
    print()

    # Run spaCy training
    print("Starting training...")
    spacy_train(
        config_path=CONFIG_PATH,
        output_path=OUTPUT_DIR,
        overrides={
            "paths.train": str(TRAIN_PATH),
            "paths.dev": str(DEV_PATH),
        },
    )

    # Load best model and evaluate on dev set
    best_model_path = OUTPUT_DIR / "model-best"
    if not best_model_path.exists():
        print("[WARN] model-best not found — checking model-last", file=sys.stderr)
        best_model_path = OUTPUT_DIR / "model-last"

    if best_model_path.exists():
        print(f"\nLoading best model from {best_model_path}...")
        nlp = spacy.load(best_model_path)
        _evaluate(nlp)
    else:
        print("[WARN] No trained model found in output directory.", file=sys.stderr)


def _evaluate(nlp) -> None:
    """Print per-category F-score on the dev set."""
    from spacy.tokens import DocBin

    db = DocBin().from_disk(DEV_PATH)
    docs = list(db.get_docs(nlp.vocab))

    # Collect true and predicted labels
    tp: dict[str, int] = {lbl: 0 for lbl in LABELS}
    fp: dict[str, int] = {lbl: 0 for lbl in LABELS}
    fn: dict[str, int] = {lbl: 0 for lbl in LABELS}

    for doc in docs:
        true_label = max(doc.cats, key=lambda k: doc.cats[k]) if doc.cats else None
        if not true_label:
            continue
        pred_doc = nlp(doc.text)
        pred_label = max(pred_doc.cats, key=lambda k: pred_doc.cats[k]) if pred_doc.cats else None

        for lbl in LABELS:
            is_true = true_label == lbl
            is_pred = pred_label == lbl
            if is_true and is_pred:
                tp[lbl] += 1
            elif not is_true and is_pred:
                fp[lbl] += 1
            elif is_true and not is_pred:
                fn[lbl] += 1

    print("\nDev set evaluation (per category):")
    print(f"  {'Category':<12} {'Precision':>9} {'Recall':>7} {'F1':>6}")
    print("  " + "-" * 38)
    macro_f1 = 0.0
    n_cats = 0
    for lbl in LABELS:
        p = tp[lbl] / (tp[lbl] + fp[lbl]) if (tp[lbl] + fp[lbl]) > 0 else 0.0
        r = tp[lbl] / (tp[lbl] + fn[lbl]) if (tp[lbl] + fn[lbl]) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        macro_f1 += f1
        n_cats += 1
        print(f"  {lbl:<12} {p:>8.1%} {r:>7.1%} {f1:>6.1%}")
    print("  " + "-" * 38)
    print(f"  {'Macro avg':<12} {'':>9} {'':>7} {macro_f1 / n_cats:>6.1%}")

    if macro_f1 / n_cats >= 0.80:
        print("\nResult: GOOD — macro F1 ≥ 80 %. Model is ready to use.")
    else:
        print(
            "\nResult: MORE DATA NEEDED — macro F1 < 80 %. "
            "Collect more labeled examples and retrain."
        )


if __name__ == "__main__":
    if not _check_prerequisites():
        sys.exit(1)
    train()
