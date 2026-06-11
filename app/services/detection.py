import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.feedback import DetectionFeedback
from app.nlp.extractor import EmailExtractor, classification_to_category
from app.nlp.llm_fallback_openai import LLMFallbackOpenAI
from app.nlp.preprocessor import truncate_email, zero_shot_classify
from app.schemas.detection import (
    EmailInput,
    ExtractionResult,
    FeedbackInput,
    FeedbackResult,
    ThreadExtractionResult,
    ValidationResult,
)
from app.schemas.email import EmailItem
from app.services.openai_service import generate_auto_reply

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


def categorize_email(email: EmailInput) -> str:
    """Classify an email using zero-shot pre-filter first, then regex + spaCy.

    Used inline in GET /emails for fast, synchronous categorization (no LLM).
    """
    cat = zero_shot_classify(email.sender, email.subject, email.body[:800], email.headers)
    if cat is not None:
        return cat
    result = _get_extractor().extract(email)
    return classification_to_category(result.classification)


def detect_single(email: EmailInput) -> ExtractionResult:
    # Zero-shot pre-filter: short-circuit for obvious automated emails
    pre_cat = zero_shot_classify(email.sender, email.subject, email.body[:800], email.headers)
    if pre_cat is not None:
        from typing import cast  # noqa: PLC0415
        from app.schemas.detection import Classification  # noqa: PLC0415
        return ExtractionResult(classification=cast(Classification, pre_cat), confidence=0.9, needs_llm=False)

    # Run extractor on truncated text for speed
    truncated = EmailInput(
        subject=email.subject,
        body=email.body[:800],
        message_id=email.message_id,
        sender=email.sender,
        headers=email.headers,
    )
    partial = _get_extractor().extract(truncated)

    # Sync LLM enhance for meeting metadata (timezone / duration / times) — unchanged
    if partial.confidence < settings.LLM_CONFIDENCE_THRESHOLD and settings.OPENAI_API_KEY:
        partial = _get_llm_fallback().enhance(email, partial)  # full body for meeting extraction

    # Safety net: if still unresolved after all layers, flag for manual review
    if partial.classification in ("other",) and partial.confidence < 0.4:
        partial.classification = "info"
        partial.needs_review = True
    return partial


async def enrich_batch(
    email_items: list[EmailItem],
    results: list[ExtractionResult],
) -> None:
    """Async enrichment phase — runs after the sync detect_batch phase.

    Pass 1: LLM category classification for emails where needs_llm=True.
    Pass 2: Auto-reply drafts for rdv / action / attente (capped at 20 per batch).

    Mutates results and email_items in-place.
    """
    # Pass 1 — async concurrent category classification for ambiguous emails
    llm_idx = [i for i, r in enumerate(results) if r.needs_llm]
    if llm_idx and settings.OPENAI_API_KEY:
        texts = [
            truncate_email(email_items[i].subject, email_items[i].body or "")
            for i in llm_idx
        ]
        classifications = await _get_llm_fallback().classify_batch_async(texts)
        for idx, llm_res in zip(llm_idx, classifications):
            if llm_res and "category" in llm_res:
                results[idx].classification = llm_res["category"]
                results[idx].confidence = float(llm_res.get("confidence", 0.8))
                results[idx].needs_llm = False

    # Pass 2 — auto-reply drafts for actionable emails (cap at 20 to limit API cost)
    reply_idx = [
        i for i, r in enumerate(results)
        if classification_to_category(r.classification) in ("rdv", "action", "attente")
    ][:20]

    if reply_idx and settings.OPENAI_API_KEY:
        async def _reply(i: int) -> tuple[int, str]:
            item = email_items[i]
            reply = await generate_auto_reply(
                subject=item.subject,
                body_truncated=(item.body or "")[:600],
                sender_name=item.sender or "",
                category=classification_to_category(results[i].classification),
            )
            return i, reply

        for entry in await asyncio.gather(
            *[_reply(i) for i in reply_idx], return_exceptions=True
        ):
            if not isinstance(entry, BaseException):
                idx, reply_text = entry  # type: ignore[misc]
                email_items[idx].suggested_reply = reply_text or None


def detect_batch(emails: list[EmailInput]) -> list[ExtractionResult]:
    if not emails:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(emails))) as executor:
        futures = {executor.submit(detect_single, e): i for i, e in enumerate(emails)}
        results: list[ExtractionResult | None] = [None] * len(emails)
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results  # type: ignore[return-value]


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
