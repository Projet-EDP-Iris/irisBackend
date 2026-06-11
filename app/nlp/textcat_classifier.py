"""
Singleton inference wrapper for the trained spaCy textcat model.

Falls back gracefully if the model has not been trained yet (returns None
so the caller can skip this layer and proceed to the LLM).

Usage:
    from app.nlp.textcat_classifier import TextcatClassifier

    clf = TextcatClassifier()
    result = clf.classify("Réunion de suivi", "Bonjour, j'aimerais planifier...")
    if result is not None:
        category, confidence = result
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).parent.parent / "ML" / "models" / "iris_textcat" / "model-best"
_FALLBACK_DIR = Path(__file__).parent.parent / "ML" / "models" / "iris_textcat" / "model-last"

LABELS = ["rdv", "action", "attente", "bonsplans", "info"]


class TextcatClassifier:
    """Lazily-loaded spaCy textcat classifier.

    Thread-safe once loaded — spaCy nlp pipelines are stateless for inference.
    """

    _instance: "TextcatClassifier | None" = None

    def __new__(cls) -> "TextcatClassifier":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._nlp = None
            cls._instance._available = None  # None = not yet checked
        return cls._instance

    @property
    def available(self) -> bool:
        if self._available is None:
            self._load()
        return bool(self._available)

    def _load(self) -> None:
        model_path = _MODEL_DIR if _MODEL_DIR.exists() else (
            _FALLBACK_DIR if _FALLBACK_DIR.exists() else None
        )
        if model_path is None:
            logger.info(
                "textcat model not found at %s — textcat layer disabled. "
                "Run: poetry run python -m app.ML.train_textcat",
                _MODEL_DIR.parent,
            )
            self._available = False
            return

        try:
            import spacy
            self._nlp = spacy.load(model_path)
            # Verify the model has a textcat component
            if "textcat" not in self._nlp.pipe_names:
                raise ValueError("Loaded model has no 'textcat' component")
            self._available = True
            logger.info("textcat model loaded from %s", model_path)
        except Exception as exc:
            logger.warning("Failed to load textcat model: %s — textcat layer disabled", exc)
            self._available = False

    def classify(self, subject: str, body: str) -> tuple[str, float] | None:
        """Classify an email into one of the 5 Iris categories.

        Returns (category, confidence) or None if the model is unavailable.
        Confidence is the raw softmax score from the textcat component (0–1).
        """
        if not self.available or self._nlp is None:
            return None

        text = f"{subject}\n{body[:800]}".strip()
        if not text:
            return None

        try:
            doc = self._nlp(text)
            if not doc.cats:
                return None
            best_label = max(doc.cats, key=lambda k: doc.cats[k])
            best_score = doc.cats[best_label]
            if best_label not in LABELS:
                return None
            return best_label, float(best_score)
        except Exception as exc:
            logger.warning("textcat inference error: %s", exc)
            return None
