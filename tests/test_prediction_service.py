import pytest

from app.schemas.detection import ExtractionResult, TimeWindow, WorkingHours
from app.schemas.prediction import CalendarAvailability, UserPreferences
from app.services.prediction_service import get_suggested_slots


def test_get_suggested_slots_minimal_extraction_returns_slots():
    extraction = ExtractionResult(
        classification="meeting_schedule",
        duration_minutes=30,
        timezone="Europe/Paris",
    )
    slots = get_suggested_slots(extraction)
    assert len(slots) > 0
    assert len(slots) <= 10
    for slot in slots:
        assert slot.start_time < slot.end_time
        assert slot.score > 0
        assert slot.label
        diff_minutes = (slot.end_time - slot.start_time).total_seconds() / 60
        assert diff_minutes == pytest.approx(30, abs=1)


def test_get_suggested_slots_uses_proposed_times_first():
    extraction = ExtractionResult(
        classification="meeting_schedule",
        duration_minutes=45,
        timezone="Europe/Paris",
        proposed_times=[
            TimeWindow(start="2026-03-15T14:00:00", end=None, timezone="Europe/Paris"),
        ],
    )
    slots = get_suggested_slots(extraction)
    assert len(slots) >= 1
    first = slots[0]
    assert first.score == 0.9
    assert (first.end_time - first.start_time).total_seconds() / 60 == pytest.approx(45, abs=1)


def test_get_suggested_slots_respects_working_hours():
    extraction = ExtractionResult(
        classification="meeting_schedule",
        duration_minutes=30,
        timezone="Europe/Paris",
    )
    preferences = UserPreferences(
        working_hours=WorkingHours(start="10:00", end="16:00", timezone="Europe/Paris"),
    )
    slots = get_suggested_slots(extraction, preferences=preferences)
    for slot in slots:
        assert slot.start_time.hour >= 10
        assert slot.end_time.hour <= 16 or (
            slot.end_time.hour == 16 and slot.end_time.minute == 0
        )


def test_get_suggested_slots_excludes_busy_slots():
    extraction = ExtractionResult(
        classification="meeting_schedule",
        duration_minutes=30,
        timezone="Europe/Paris",
        proposed_times=[
            TimeWindow(start="2026-03-20T10:00:00", end="2026-03-20T10:30:00", timezone="Europe/Paris"),
            TimeWindow(start="2026-03-20T11:00:00", end="2026-03-20T11:30:00", timezone="Europe/Paris"),
        ],
    )
    calendar = CalendarAvailability(
        busy_slots=[
            TimeWindow(start="2026-03-20T10:00:00", end="2026-03-20T11:00:00", timezone="Europe/Paris"),
        ],
    )
    slots = get_suggested_slots(extraction, calendar=calendar)
    for slot in slots:
        slot_start = slot.start_time
        slot_end = slot.end_time
        assert not (
            slot_start.hour == 10
            and slot_start.minute == 0
            and slot_end.hour == 10
            and slot_end.minute == 30
        ), "Slot at 10:00-10:30 should be excluded (overlaps busy)"


def test_get_suggested_slots_uses_preferred_duration_when_extraction_has_none():
    extraction = ExtractionResult(
        classification="meeting_schedule",
        duration_minutes=None,
        timezone="Europe/Paris",
    )
    preferences = UserPreferences(preferred_duration_minutes=60)
    slots = get_suggested_slots(extraction, preferences=preferences)
    assert len(slots) > 0
    for slot in slots:
        diff_minutes = (slot.end_time - slot.start_time).total_seconds() / 60
        assert diff_minutes == pytest.approx(60, abs=1)


def test_get_suggested_slots_empty_extraction_returns_default_duration_slots():
    extraction = ExtractionResult()
    slots = get_suggested_slots(extraction)
    assert isinstance(slots, list)
    if slots:
        diff_minutes = (slots[0].end_time - slots[0].start_time).total_seconds() / 60
        assert diff_minutes == pytest.approx(30, abs=1)
