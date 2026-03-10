from datetime import datetime

import pendulum

from app.schemas.detection import ExtractionResult, TimeWindow
from app.schemas.prediction import (
    CalendarAvailability,
    RecommendedSlot,
    UserPreferences,
)

DEFAULT_TIMEZONE = "Europe/Paris"
DEFAULT_DURATION_MINUTES = 30
MAX_SLOTS_RETURNED = 10
CANDIDATE_DAYS_AHEAD = 14
HOUR_STEP = 1


def _resolve_duration_minutes(extraction: ExtractionResult, preferences: UserPreferences | None) -> int:
    if extraction.duration_minutes is not None:
        return extraction.duration_minutes
    if preferences and preferences.preferred_duration_minutes is not None:
        return preferences.preferred_duration_minutes
    return DEFAULT_DURATION_MINUTES


def _resolve_timezone(extraction: ExtractionResult, preferences: UserPreferences | None) -> str:
    if extraction.timezone:
        return extraction.timezone
    if preferences and preferences.timezone:
        return preferences.timezone
    if preferences and preferences.working_hours and preferences.working_hours.timezone:
        return preferences.working_hours.timezone
    return DEFAULT_TIMEZONE


def _parse_window_start(tw: TimeWindow, tz: str) -> pendulum.DateTime | None:
    if not tw.start:
        return None
    try:
        dt = pendulum.parse(tw.start, tz=tz)
        return dt if isinstance(dt, pendulum.DateTime) else pendulum.datetime(
            dt.year, dt.month, dt.day, dt.hour, dt.minute, tz=tz
        )
    except Exception:
        return None


def _candidates_from_proposed_times(
    extraction: ExtractionResult, duration_minutes: int, tz: str
) -> list[tuple[pendulum.DateTime, pendulum.DateTime, float]]:
    """Return (start, end, score) for each proposed time. Score 0.9 for proposed."""
    out: list[tuple[pendulum.DateTime, pendulum.DateTime, float]] = []
    for tw in extraction.proposed_times[:10]:
        start = _parse_window_start(tw, tz)
        if start is None:
            continue
        end = start.add(minutes=duration_minutes)
        out.append((start, end, 0.9))
    return out


def _candidates_from_defaults(
    duration_minutes: int,
    tz: str,
    working_start: int | None,
    working_end: int | None,
) -> list[tuple[pendulum.DateTime, pendulum.DateTime, float]]:
    """Generate default candidates: next CANDIDATE_DAYS_AHEAD days, hourly steps. Score 0.7."""
    out: list[tuple[pendulum.DateTime, pendulum.DateTime, float]] = []
    now = pendulum.now(tz)
    start_hour = working_start if working_start is not None else 9
    end_hour = working_end if working_end is not None else 18

    for day_offset in range(CANDIDATE_DAYS_AHEAD):
        day = now.add(days=day_offset).start_of("day")
        for hour in range(start_hour, end_hour, HOUR_STEP):
            slot_start = day.add(hours=hour)
            if slot_start < now:
                continue
            slot_end = slot_start.add(minutes=duration_minutes)
            if slot_end.hour > end_hour or (slot_end.hour == end_hour and slot_end.minute > 0):
                continue
            out.append((slot_start, slot_end, 0.7))
            if len(out) >= MAX_SLOTS_RETURNED * 2:
                return out
    return out


def _working_hours_bounds(preferences: UserPreferences | None) -> tuple[int | None, int | None]:
    if not preferences or not preferences.working_hours:
        return None, None
    wh = preferences.working_hours
    start_h = None
    end_h = None
    if wh.start:
        try:
            parts = wh.start.replace(":", " ").split()
            start_h = int(parts[0]) if parts else 9
        except (ValueError, IndexError):
            start_h = 9
    if wh.end:
        try:
            parts = wh.end.replace(":", " ").split()
            end_h = int(parts[0]) if parts else 18
        except (ValueError, IndexError):
            end_h = 18
    return start_h, end_h


def _slot_overlaps_busy(
    slot_start: pendulum.DateTime,
    slot_end: pendulum.DateTime,
    busy_slots: list[TimeWindow],
    tz: str,
) -> bool:
    for tw in busy_slots or []:
        busy_start = _parse_window_start(tw, tz)
        if busy_start is None:
            continue
        busy_end = tw.end
        if busy_end:
            try:
                busy_end_dt = pendulum.parse(busy_end, tz=tz)
            except Exception:
                busy_end_dt = busy_start.add(hours=1)
        else:
            busy_end_dt = busy_start.add(hours=1)
        if slot_start < busy_end_dt and slot_end > busy_start:
            return True
    return False


def _to_recommended_slot(
    start: pendulum.DateTime,
    end: pendulum.DateTime,
    score: float,
    intent: str,
) -> RecommendedSlot:
    return RecommendedSlot(
        start_time=start,
        end_time=end,
        score=score,
        label=f"Créneau pour {intent}",
    )


def get_suggested_slots(
    extraction: ExtractionResult,
    preferences: UserPreferences | None = None,
    calendar: CalendarAvailability | None = None,
) -> list[RecommendedSlot]:
    duration_minutes = _resolve_duration_minutes(extraction, preferences)
    tz = _resolve_timezone(extraction, preferences)
    intent = extraction.classification if extraction.classification != "other" else "meeting"
    working_start, working_end = _working_hours_bounds(preferences)

    candidates: list[tuple[pendulum.DateTime, pendulum.DateTime, float]] = []
    if extraction.proposed_times:
        candidates = _candidates_from_proposed_times(extraction, duration_minutes, tz)
    if not candidates:
        candidates = _candidates_from_defaults(
            duration_minutes, tz, working_start, working_end
        )

    busy_slots = calendar.busy_slots if calendar else None
    filtered: list[tuple[pendulum.DateTime, pendulum.DateTime, float]] = []
    for start, end, score in candidates:
        if busy_slots and _slot_overlaps_busy(start, end, busy_slots, tz):
            continue
        if working_start is not None:
            end_h = working_end if working_end is not None else 18
            if start.hour < working_start or end.hour > end_h or (end.hour == end_h and end.minute > 0):
                continue
        filtered.append((start, end, score))

    filtered.sort(key=lambda x: (x[0], -x[2]))
    seen: set[tuple[pendulum.DateTime, pendulum.DateTime]] = set()
    unique: list[tuple[pendulum.DateTime, pendulum.DateTime, float]] = []
    for start, end, score in filtered:
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        unique.append((start, end, score))
        if len(unique) >= MAX_SLOTS_RETURNED:
            break

    return [
        _to_recommended_slot(start, end, score, intent)
        for start, end, score in unique
    ]
