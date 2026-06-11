"""
Export labeled emails from the DB to spaCy binary training format.

Usage:
    cd irisBackend
    poetry run python -m app.ML.export_training_data

Output:
    app/ML/data/train.spacy  (80 % of examples)
    app/ML/data/dev.spacy    (20 % of examples)

Data sources (in priority order):
    1. DetectionFeedback table — gold labels from explicit user corrections
    2. Email table — pipeline-assigned labels with confidence > 0.70

Labels: rdv, action, attente, bonsplans, info
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LABELS = ["rdv", "action", "attente", "bonsplans", "info"]

# Maps the 7 internal classification values to the 5 UI labels
_CLASSIFICATION_TO_LABEL = {
    "meeting_schedule":   "rdv",
    "meeting_cancel":     "rdv",
    "meeting_reschedule": "rdv",
    "action":             "action",
    "attente":            "attente",
    "bonsplans":          "bonsplans",
    "info":               "info",
    "other":              "info",
}


def _make_cats(label: str) -> dict[str, float]:
    return {lbl: (1.0 if lbl == label else 0.0) for lbl in LABELS}


def _load_from_db() -> list[tuple[str, str]]:
    """Return (text, label) pairs from the DB.

    Priority:
      1. DetectionFeedback corrections (gold labels)
      2. Email rows with category != null and extraction confidence > 0.70
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sql_text
        db_url = "sqlite:///" + str(ROOT / "test.db")
        engine = create_engine(db_url)
    except Exception as exc:
        print(f"[ERROR] Cannot connect to database: {exc}", file=sys.stderr)
        return []

    examples: list[tuple[str, str]] = []
    seen_ids: set[int] = set()  # email ids already covered by gold labels

    with engine.connect() as conn:
        # 1. Gold labels from user corrections
        try:
            rows = conn.execute(
                sql_text("SELECT original_extraction, corrections FROM detection_feedback")
            ).fetchall()
            for row in rows:
                orig = json.loads(row[0]) if row[0] else {}
                corr = json.loads(row[1]) if row[1] else {}
                label = corr.get("classification") or corr.get("category")
                if not label:
                    continue
                label = _CLASSIFICATION_TO_LABEL.get(label, label)
                if label not in LABELS:
                    continue
                subject = orig.get("subject", "")
                body = orig.get("body", "")
                if not body and not subject:
                    continue
                text = f"{subject}\n{body[:800]}".strip()
                examples.append((text, label))
                email_id = orig.get("email_id")
                if email_id:
                    seen_ids.add(int(email_id))
        except Exception as exc:
            print(f"[WARN] Could not read detection_feedback: {exc}", file=sys.stderr)

        # 2. Emails from the main table (skip those already covered by feedback)
        try:
            rows = conn.execute(
                sql_text(
                    "SELECT id, subject, body, category, extraction_data "
                    "FROM emails "
                    "WHERE category IS NOT NULL AND body IS NOT NULL AND body != ''"
                )
            ).fetchall()
            for row in rows:
                email_id, subject, body, category, extraction_json = row
                if email_id in seen_ids:
                    continue

                # Skip low-confidence pipeline labels
                confidence = 0.0
                if extraction_json:
                    try:
                        extraction_json_str = extraction_json if isinstance(extraction_json, str) else json.dumps(extraction_json)
                        extraction = json.loads(extraction_json_str)
                        confidence = float(extraction.get("confidence", 0.0))
                    except (ValueError, TypeError):
                        pass
                if confidence < 0.70:
                    continue

                label = _CLASSIFICATION_TO_LABEL.get(category, category)
                if label not in LABELS:
                    continue

                subject = subject or ""
                body = body or ""
                text = f"{subject}\n{body[:800]}".strip()
                if not text:
                    continue
                examples.append((text, label))
        except Exception as exc:
            print(f"[WARN] Could not read emails table: {exc}", file=sys.stderr)

    return examples


def _to_spacy_docbin(examples: list[tuple[str, str]]):
    """Convert (text, label) pairs to a spaCy DocBin."""
    import spacy
    from spacy.tokens import DocBin

    nlp = spacy.blank("fr")
    db = DocBin()
    for text, label in examples:
        doc = nlp.make_doc(text)
        doc.cats = _make_cats(label)
        db.add(doc)
    return db


def main() -> None:
    print("Loading labeled emails from database...")
    examples = _load_from_db()

    if not examples:
        print(
            "[ERROR] No labeled examples found. "
            "Make sure the DB has classified emails (category IS NOT NULL).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Shuffle and split 80/20
    random.seed(42)
    random.shuffle(examples)
    split = int(len(examples) * 0.8)
    train_examples = examples[:split]
    dev_examples = examples[split:]

    # Print label distribution
    from collections import Counter
    print(f"\nTotal examples: {len(examples)}")
    print("Label distribution:")
    for label, count in sorted(Counter(lbl for _, lbl in examples).items()):
        print(f"  {label:<12} {count:>4} examples")

    print(f"\nTrain: {len(train_examples)}   Dev: {len(dev_examples)}")

    # Write spaCy binary files
    train_path = DATA_DIR / "train.spacy"
    dev_path = DATA_DIR / "dev.spacy"

    _to_spacy_docbin(train_examples).to_disk(train_path)
    _to_spacy_docbin(dev_examples).to_disk(dev_path)

    print(f"\nWrote: {train_path}")
    print(f"Wrote: {dev_path}")

    # Warn if any category is thin
    counts = Counter(lbl for _, lbl in examples)
    thin = [lbl for lbl in LABELS if counts.get(lbl, 0) < 100]
    if thin:
        print(
            f"\n[WARN] Low example count for: {', '.join(thin)}. "
            "Accuracy will be lower for these categories. "
            "Target 300–500 examples per category for best results."
        )
    else:
        print("\nAll categories have ≥ 100 examples.")


if __name__ == "__main__":
    main()
