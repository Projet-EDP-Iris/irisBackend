"""
Script d'analyse des feedbacks utilisateurs pour améliorer le tri des emails.

Usage:
    cd irisBackend
    python -m app.ML.retrain_from_feedback

Sortie: app/ML/feedback_patterns_report.json
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent.parent
REPORT_PATH = Path(__file__).parent / "feedback_patterns_report.json"

# ---------------------------------------------------------------------------
# Accès base de données
# ---------------------------------------------------------------------------

def _load_feedbacks() -> list[dict]:
    """Lit tous les feedbacks depuis la DB SQLite du projet."""
    try:
        from sqlalchemy import create_engine, text
        db_url = "sqlite:///" + str(ROOT / "test.db")
        engine = create_engine(db_url)
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT original_extraction, corrections FROM detection_feedback")).fetchall()
        return [
            {
                "original": json.loads(r[0]) if r[0] else {},
                "correction": json.loads(r[1]) if r[1] else {},
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[WARN] Impossible de lire la DB : {e}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Extraction de tokens discriminants (TF-IDF simplifié)
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "à", "au",
    "que", "qui", "ce", "je", "tu", "il", "elle", "nous", "vous", "ils",
    "the", "a", "an", "of", "to", "in", "is", "it", "for", "on", "with",
    "this", "that", "have", "has", "are", "was", "be", "been", "or", "not",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zàâäéèêëîïôùûüçœæ]{3,}", text.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def _top_tokens(texts: list[str], n: int = 20) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for t in texts:
        counter.update(_tokenize(t))
    return counter.most_common(n)


# ---------------------------------------------------------------------------
# Analyse principale
# ---------------------------------------------------------------------------

def analyze(feedbacks: list[dict]) -> dict:
    misclassified: list[dict] = []
    for fb in feedbacks:
        orig_cls = fb["original"].get("classification")
        corr_cls = fb["correction"].get("classification")
        if orig_cls and corr_cls and orig_cls != corr_cls:
            misclassified.append(fb)

    total = len(feedbacks)
    errors = len(misclassified)
    accuracy = round(1 - errors / total, 4) if total > 0 else 1.0

    # Compter les transitions (quelle catégorie a été mal prédite vers quelle autre)
    transitions: Counter = Counter()
    category_texts: dict[str, list[str]] = defaultdict(list)

    for fb in misclassified:
        orig = fb["original"].get("classification", "?")
        corr = fb["correction"].get("classification", "?")
        transitions[(orig, corr)] += 1
        # Collecter le texte source pour extraire des patterns
        subject = fb["original"].get("subject", "")
        body = fb["original"].get("body", "")
        category_texts[corr].append(f"{subject} {body}")

    # Top tokens pour chaque catégorie mal classée
    pattern_suggestions: dict[str, list[str]] = {}
    for cat, texts in category_texts.items():
        top = _top_tokens(texts, n=15)
        pattern_suggestions[cat] = [word for word, _ in top]

    # Résumé des transitions les plus fréquentes
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
            "Ajouter les mots-clés listés dans 'suggested_patterns_by_category' "
            "aux regex correspondantes dans irisBackend/app/nlp/extractor.py "
            "pour réduire les erreurs de classification."
        ),
    }


# ---------------------------------------------------------------------------
# Entrée principale
# ---------------------------------------------------------------------------

def main() -> None:
    print("Chargement des feedbacks...")
    feedbacks = _load_feedbacks()

    if not feedbacks:
        print("Aucun feedback trouvé. Créez des corrections via POST /api/v1/feedback d'abord.")
        return

    print(f"{len(feedbacks)} feedback(s) trouvé(s). Analyse en cours...")
    report = analyze(feedbacks)

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRapport écrit dans : {REPORT_PATH}")
    print(f"Précision actuelle : {report['summary']['accuracy_rate'] * 100:.1f}%")
    print(f"Emails mal classés : {report['summary']['misclassified']} / {report['summary']['total_feedbacks']}")

    if report["top_misclassification_transitions"]:
        print("\nTop erreurs de classification :")
        for t in report["top_misclassification_transitions"][:5]:
            print(f"  {t['from']} → {t['to']} : {t['count']} fois")

    if report["suggested_patterns_by_category"]:
        print("\nPatterns suggérés à ajouter dans extractor.py :")
        for cat, words in report["suggested_patterns_by_category"].items():
            print(f"  [{cat}] {', '.join(words)}")


if __name__ == "__main__":
    main()
