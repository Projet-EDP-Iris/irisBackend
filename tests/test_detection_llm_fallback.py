from unittest.mock import MagicMock

import pytest

from app.nlp.llm_fallback_openai import LLMFallbackOpenAI, _merge_patch
from app.schemas.detection import EmailInput, ExtractionResult


@pytest.fixture
def low_confidence_result():
    return ExtractionResult(
        classification="meeting_schedule",
        proposed_times=[],
        duration_minutes=None,
        timezone=None,
        confidence=0.35,
    )


@pytest.fixture
def email():
    return EmailInput(subject="Meeting", body="Call tomorrow at 3pm.")


def test_enhance_returns_partial_when_no_api_key(monkeypatch, email, low_confidence_result):
    monkeypatch.setattr("app.nlp.llm_fallback_openai.settings.OPENAI_API_KEY", None)
    fallback = LLMFallbackOpenAI()
    result = fallback.enhance(email, low_confidence_result)
    assert result.confidence == 0.35
    assert result.timezone is None


def test_enhance_skips_llm_when_confidence_above_threshold(monkeypatch, email):
    monkeypatch.setattr("app.nlp.llm_fallback_openai.settings.OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("app.nlp.llm_fallback_openai.settings.LLM_CONFIDENCE_THRESHOLD", 0.6)
    high_result = ExtractionResult(classification="meeting_schedule", confidence=0.8)
    fallback = LLMFallbackOpenAI()
    result = fallback.enhance(email, high_result)
    assert result.confidence == 0.8


def test_enhance_merges_patch_only_missing_fields(monkeypatch, email, low_confidence_result):
    monkeypatch.setattr("app.nlp.llm_fallback_openai.settings.OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("app.nlp.llm_fallback_openai.settings.LLM_CONFIDENCE_THRESHOLD", 0.6)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='{"timezone": "Europe/Paris", "duration_minutes": 30}'))]
    )
    fallback = LLMFallbackOpenAI()
    fallback._client = mock_client
    result = fallback.enhance(email, low_confidence_result)
    assert result.timezone == "Europe/Paris"
    assert result.duration_minutes == 30
    assert result.confidence >= 0.35


def test_merge_patch_fills_only_empty():
    partial = ExtractionResult(
        classification="meeting_schedule",
        timezone="UTC",
        duration_minutes=None,
        confidence=0.4,
    )
    patch = {"timezone": "EST", "duration_minutes": 60}
    merged = _merge_patch(partial, patch)
    assert merged.timezone == "UTC"
    assert merged.duration_minutes == 60
    assert merged.confidence >= 0.4


def test_merge_patch_proposed_times():
    partial = ExtractionResult(
        classification="meeting_schedule",
        proposed_times=[],
        confidence=0.3,
    )
    patch = {"proposed_times": [{"start": "2025-03-01T14:00:00", "end": None, "timezone": None}]}
    merged = _merge_patch(partial, patch)
    assert len(merged.proposed_times) == 1
    assert merged.proposed_times[0].start == "2025-03-01T14:00:00"
