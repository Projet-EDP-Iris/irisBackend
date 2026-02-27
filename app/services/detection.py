import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.feedback import DetectionFeedback
from app.nlp.extractor import EmailExtractor
from app.nlp.llm_fallback_openai import LLMFallbackOpenAI
from app.schemas.detection import (
    EmailInput,
    ExtractionResult,
    FeedbackInput,
    FeedbackResult,
    ThreadExtractionResult,
    ValidationResult,
)

_extractor: EmailExtractor | None = None
_llm_fallback: LLMFallbackOpenAI | None = None


def _get_extractor() -> EmailExtractor:
    global _extractor
    if _extractor is None:
        _extractor = EmailExtractor(model_name=settings.NLP_MODEL_PATH)
    return _extractor


def _get_llm_fallback() -> LLMFallbackOpenAI:
    global _llm_fallback
    if _llm_fallback is None:
        _llm_fallback = LLMFallbackOpenAI()
    return _llm_fallback


def detect_single(email: EmailInput) -> ExtractionResult:
    extractor = _get_extractor()
    partial = extractor.extract(email)
    if partial.confidence < settings.LLM_CONFIDENCE_THRESHOLD and settings.OPENAI_API_KEY:
        partial = _get_llm_fallback().enhance(email, partial)
    return partial


def detect_batch(emails: list[EmailInput]) -> list[ExtractionResult]:
    return [detect_single(e) for e in emails]


def _merge_thread_results(results: list[ExtractionResult]) -> ExtractionResult:
    if not results:
        return ExtractionResult()
    merged = results[-1].model_copy(deep=True)
    merged.thread_status = results[-1].thread_status
    all_times = []
    seen = set()
    for r in results:
        for tw in r.proposed_times:
            key = (tw.start, tw.end, tw.timezone)
            if key not in seen:
                seen.add(key)
                all_times.append(tw)
    merged.proposed_times = all_times[:10]
    return merged


def detect_thread(messages: list[EmailInput]) -> ThreadExtractionResult:
    if not messages:
        return ThreadExtractionResult(merged=ExtractionResult(), message_results=[])
    results = [detect_single(m) for m in messages]
    merged = _merge_thread_results(results)
    return ThreadExtractionResult(merged=merged, message_results=results)


REQUIRED_FIELDS = ["classification", "proposed_times", "timezone", "duration_minutes"]
CLARIFYING = {
    "timezone": "What timezone should we use?",
    "duration_minutes": "How long should the meeting be?",
    "proposed_times": "When are you available?",
    "classification": "Is this a scheduling, cancellation, or other request?",
}


def validate_extraction(extraction: dict) -> ValidationResult:
    missing = []
    questions = []
    for field in REQUIRED_FIELDS:
        val = extraction.get(field)
        if val is None or (isinstance(val, list) and len(val) == 0):
            missing.append(field)
            if field in CLARIFYING:
                questions.append(CLARIFYING[field])
    classification = extraction.get("classification")
    if classification == "meeting_schedule" and missing:
        valid = False
    else:
        valid = len(missing) == 0
    return ValidationResult(
        valid=valid,
        missing_fields=missing,
        clarifying_questions=questions,
    )


def save_feedback(
    feedback: FeedbackInput,
    db: Session,
    user_id: int | None = None,
) -> FeedbackResult:
    row = DetectionFeedback(
        message_id=feedback.message_id,
        user_id=user_id,
        original_extraction=json.dumps(feedback.original_extraction),
        corrections=json.dumps(feedback.corrections),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FeedbackResult(feedback_id=row.id)
