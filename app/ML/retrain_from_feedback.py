"""
Analyses user feedback stored in the database to identify classification errors
and suggest new regex patterns for extractor.py.

Usage:
    cd irisBackend
    python -m app.ML.retrain_from_feedback

Output: app/ML/feedback_patterns_report.json
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
REPORT_PATH = Path(__file__).parent / "feedback_patterns_report.json"

STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "à", "au",
    "que", "qui", "ce", "je", "tu", "il", "elle", "nous", "vous", "ils",
    "the", "a", "an", "of", "to", "in", "is", "it", "for", "on", "with",
    "this", "that", "have", "has", "are", "was", "be", "been", "or", "not",
}


def _load_feedbacks() -> list[dict]:
    """Load all user correction feedback from the SQLite database."""
    try:
        from sqlalchemy import create_engine, text
        db_url = "sqlite:///" + str(ROOT / "test.db")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT original_extraction, corrections FROM detection_feedback")
            ).fetchall()
        return [
            {
                "original": json.loads(r[0]) if r[0] else {},
                "correction": json.loads(r[1]) if r[1] else {},
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[WARN] Could not read database: {e}", file=sys.stderr)
        return []


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zàâäéèêëîïôùûüçœæ]{3,}", text.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def _top_tokens(texts: list[str], n: int = 20) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for t in texts:
        counter.update(_tokenize(t))
    return counter.most_common(n)


def analyze(feedbacks: list[dict]) -> dict:
    """
    Identify misclassified emails and compute per-category token frequencies.

    Returns a report containing:
    - summary: total feedback count, error count, accuracy rate
    - top_misclassification_transitions: which categories are confused most often
    - suggested_patterns_by_category: top tokens from misclassified emails per category
    - recommendation: human-readable next step
    """
    misclassified = [
        fb for fb in feedbacks
        if fb["original"].get("classification") != fb["correction"].get("classification")
        and fb["original"].get("classification")
        and fb["correction"].get("classification")
    ]

    total = len(feedbacks)
    errors = len(misclassified)
    accuracy = round(1 - errors / total, 4) if total > 0 else 1.0

    transitions: Counter = Counter()
    category_texts: dict[str, list[str]] = defaultdict(list)

    for fb in misclassified:
        orig = fb["original"].get("classification", "?")
        corr = fb["correction"].get("classification", "?")
        transitions[(orig, corr)] += 1
        subject = fb["original"].get("subject", "")
        body = fb["original"].get("body", "")
        category_texts[corr].append(f"{subject} {body}")

    pattern_suggestions = {
        cat: [word for word, _ in _top_tokens(texts, n=15)]
        for cat, texts in category_texts.items()
    }
    top_transitions = [
        {"from": k[0], "to": k[1], "count": v}
        for k, v in transitions.most_common(10)
    ]

    return {
        "summary": {
            "total_feedbacks": total,
            "misclassified": errors,
            "accuracy_rate": accuracy,
        },
        "top_misclassification_transitions": top_transitions,
        "suggested_patterns_by_category": pattern_suggestions,
        "recommendation": (
            "Add the keywords listed in 'suggested_patterns_by_category' "
            "to the matching regexes in irisBackend/app/nlp/extractor.py "
            "to reduce classification errors."
        ),
    }


def main() -> None:
    print("Loading feedback...")
    feedbacks = _load_feedbacks()

    if not feedbacks:
        print("No feedback found. Submit corrections via POST /api/v1/feedback first.")
        return

    print(f"{len(feedbacks)} feedback record(s) found. Analysing...")
    report = analyze(feedbacks)

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")
    print(f"Current accuracy: {report['summary']['accuracy_rate'] * 100:.1f}%")
    print(f"Misclassified: {report['summary']['misclassified']} / {report['summary']['total_feedbacks']}")

    if report["top_misclassification_transitions"]:
        print("\nTop misclassification transitions:")
        for t in report["top_misclassification_transitions"][:5]:
            print(f"  {t['from']} → {t['to']}: {t['count']} time(s)")

    if report["suggested_patterns_by_category"]:
        print("\nSuggested patterns to add to extractor.py:")
        for cat, words in report["suggested_patterns_by_category"].items():
            print(f"  [{cat}] {', '.join(words)}")


if __name__ == "__main__":
    main()
