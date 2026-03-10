# Detection API — PR Summary

## Files changed

**New**
- `app/schemas/detection.py` — Input/output schemas (EmailInput, EmailBatchInput, ThreadInput, ValidationInput, FeedbackInput; ExtractionResult, ThreadExtractionResult, ValidationResult, FeedbackResult, DetectResponse; value types WorkingHours, TimeWindow, Participant, Constraint)
- `app/nlp/extractor.py` — EmailExtractor (spaCy + dateparser + regex), intent classification EN/FR, time/duration/timezone/modality/participants/thread_status, confidence and needs_clarification
- `app/nlp/llm_fallback_openai.py` — LLMFallbackOpenAI.enhance (optional OpenAI structured-output patch, merge into partial, no overwrite of existing fields)
- `app/services/detection.py` — detect_single, detect_batch, detect_thread (merge), validate_extraction, save_feedback; lazy singleton extractor and LLM fallback
- `app/api/routes/detection.py` — POST /detect, /detect/thread, /validate, /feedback (all JWT-protected)
- `app/models/feedback.py` — DetectionFeedback table (id, message_id, user_id, original_extraction, corrections)
- `tests/test_detection_extractor_unit.py` — Unit tests for extractor (EN/FR scheduling, cancellation, needs_clarification)
- `tests/test_detection_llm_fallback.py` — LLM fallback tests (no key → no call, high confidence → no call, patch merge)
- `tests/test_detection_api.py` — Integration tests (401/403 without auth, /detect EN/FR/cancel/batch, /detect/thread confirmed, /validate missing timezone, /feedback DB row)

**Modified**
- `app/core/config.py` — OPENAI_API_KEY, LLM_CONFIDENCE_THRESHOLD
- `app/main.py` — include detection router
- `app/models/__init__.py` — export DetectionFeedback
- `app/db/database.py` — import DetectionFeedback for create_all
- `pyproject.toml` — dateparser, openai
- `.env.example` — OPENAI_API_KEY=

## How to run tests

```bash
# From project root (with deps installed, e.g. uv sync or pip install -e ".[dev]")
pytest
# Or only detection-related:
pytest tests/test_detection_extractor_unit.py tests/test_detection_llm_fallback.py tests/test_detection_api.py
```

## How to call endpoints

All detection endpoints require JWT: `Authorization: Bearer <access_token>` (obtain token via `POST /users/login`).

- **POST /detect** — Single or batch (list of one or more).  
  Body: `{ "emails": [ { "subject": "...", "body": "...", "message_id": "optional" } ] }`  
  Response: `{ "results": [ ExtractionResult, ... ] }`

- **POST /detect/thread** — Thread of messages.  
  Body: `{ "messages": [ { "subject": "...", "body": "..." }, ... ] }`  
  Response: `ThreadExtractionResult` (merged + message_results)

- **POST /validate** — Validate an extraction.  
  Body: `{ "extraction": { ... } }`  
  Response: `{ "valid": bool, "missing_fields": [...], "clarifying_questions": [...] }`

- **POST /feedback** — Persist feedback (only endpoint that writes to DB).  
  Body: `{ "message_id": "...", "original_extraction": { ... }, "corrections": { ... } }`  
  Response: `{ "feedback_id": int }`

## Notes

- If `OPENAI_API_KEY` is unset, the app uses spaCy-only extraction (no crash, no warning).
- No raw email content or API keys are logged.
- OpenAI usage in tests is disabled via `OPENAI_API_KEY` in integration tests and mocked in LLM fallback unit tests.
