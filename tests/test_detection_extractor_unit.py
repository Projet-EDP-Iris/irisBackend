import pytest

from app.nlp.extractor import EmailExtractor
from app.schemas.detection import EmailInput


@pytest.fixture
def extractor():
    return EmailExtractor(model_name="fr_core_news_sm")


def test_english_scheduling_email_classification(extractor):
    email = EmailInput(
        subject="Meeting tomorrow",
        body="Can we schedule a call tomorrow at 3pm? I'm available.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_schedule"
    assert result.confidence >= 0.3


def test_english_scheduling_email_with_proposed_time(extractor):
    email = EmailInput(
        subject="Call next week",
        body="Let's meet on Tuesday March 4 at 2:30 PM for 30 minutes. Zoom link: https://zoom.us/j/123.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_schedule"
    assert len(result.proposed_times) >= 1
    assert result.duration_minutes == 30
    assert result.meeting_link is not None


def test_french_scheduling_email(extractor):
    email = EmailInput(
        subject="Réunion",
        body="Réunion mardi prochain à 10h. Merci.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_schedule"


def test_cancellation_email(extractor):
    email = EmailInput(
        subject="Meeting cancelled",
        body="Sorry, the meeting is cancelled. We'll reschedule later.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_cancel"


def test_cancellation_french(extractor):
    email = EmailInput(
        subject="Annulation",
        body="La réunion est annulée.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_cancel"


def test_needs_clarification_when_timezone_missing(extractor):
    email = EmailInput(
        subject="Meeting",
        body="Schedule a call tomorrow at 3pm. No timezone mentioned.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_schedule"
    assert result.needs_clarification is True


def test_needs_clarification_when_duration_missing(extractor):
    email = EmailInput(
        subject="Call",
        body="Let's meet Tuesday at 10am in Paris.",
    )
    result = extractor.extract(email)
    if result.classification == "meeting_schedule":
        assert result.needs_clarification is True


def test_empty_email(extractor):
    email = EmailInput(subject="", body="")
    result = extractor.extract(email)
    assert result.classification == "other"
    assert result.confidence == 0.0
