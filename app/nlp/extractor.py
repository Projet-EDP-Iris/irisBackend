import re
from datetime import datetime

from app.schemas.detection import (
    Classification,
    EmailInput,
    ExtractionResult,
    Participant,
    ThreadStatusLiteral,
    TimeWindow,
)

SCHEDULE_EN = re.compile(
    r"\b(meeting|schedule|call|appointment|réunion|rendez-vous|planifier|"
    r"meet|book|slot|availability|available|mardi|mercredi|lundi|jeudi|vendredi)\b",
    re.IGNORECASE,
)
CANCEL_EN = re.compile(
    r"\b(cancel|cancelled|cancellation|annul|annulé|annulation|postpone|reporté|"
    r"call off|won't happen|ne pourra pas)\b",
    re.IGNORECASE,
)
RESCHEDULE_EN = re.compile(
    r"\b(reschedule|move|déplacer|reporter|new time|nouvelle date|change of time)\b",
    re.IGNORECASE,
)
DURATION_RE = re.compile(
    r"(\d+)\s*(?:min(?:ute)?s?|h(?:our)?s?|hrs?)\b",
    re.IGNORECASE,
)
TZ_RE = re.compile(
    r"\b(UTC[+-]?\d+|EST|EDT|CST|PST|CET|CEST|Europe/\w+|America/\w+)\b",
    re.IGNORECASE,
)
LINK_RE = re.compile(r"https?://[^\s<>]+")
MODALITY_RE = re.compile(
    r"\b(zoom|meet\.google|teams\.microsoft|webex|gotomeeting)\b",
    re.IGNORECASE,
)
FROM_TO_RE = re.compile(
    r"(?:^|\n)\s*(?:from|de|to|à)\s*:?\s*([^\n<@]+@[^\s>]+|[^\n<@]+)",
    re.IGNORECASE | re.MULTILINE,
)
CONFIRMED_RE = re.compile(
    r"\b(confirmed|confirmé|accepted|accepté|ok|d'accord)\b",
    re.IGNORECASE,
)
CANCELLED_RE = re.compile(
    r"\b(cancelled|canceled|annulé)\b",
    re.IGNORECASE,
)


def _load_nlp(model_name: str):
    try:
        import spacy
        return spacy.load(model_name)
    except Exception:
        return None


def _classify(text: str) -> Classification:
    if CANCEL_EN.search(text):
        return "meeting_cancel"
    if RESCHEDULE_EN.search(text):
        return "meeting_reschedule"
    if SCHEDULE_EN.search(text):
        return "meeting_schedule"
    return "other"


def _extract_times(text: str) -> list[TimeWindow]:
    out: list[TimeWindow] = []
    try:
        import dateparser.search
        results = dateparser.search.search_dates(text, settings={"PREFER_DATES_FROM": "future"})
        if results:
            for _phrase, dt in results[:5]:
                if isinstance(dt, datetime):
                    out.append(
                        TimeWindow(
                            start=dt.isoformat(),
                            end=None,
                            timezone=None,
                        )
                    )
    except Exception:
        pass
    return out


def _extract_duration_minutes(text: str) -> int | None:
    m = DURATION_RE.search(text)
    if not m:
        return None
    num = int(m.group(1))
    unit = m.group(0).lower()
    if "h" in unit and "min" not in unit:
        return num * 60
    return num


def _extract_timezone(text: str) -> str | None:
    m = TZ_RE.search(text)
    return m.group(1) if m else None


def _extract_meeting_link(text: str) -> str | None:
    m = LINK_RE.search(text)
    return m.group(0) if m else None


def _extract_modality(text: str) -> str | None:
    m = MODALITY_RE.search(text)
    return m.group(1).lower() if m else None


def _extract_participants(text: str) -> list[Participant]:
    participants: list[Participant] = []
    for m in FROM_TO_RE.finditer(text):
        raw = m.group(1).strip()
        if "@" in raw:
            participants.append(Participant(email=raw, name=None))
        else:
            participants.append(Participant(email=None, name=raw))
    return participants[:10]


def _thread_status(text: str) -> ThreadStatusLiteral:
    if CANCELLED_RE.search(text):
        return "cancelled"
    if CONFIRMED_RE.search(text):
        return "confirmed"
    if SCHEDULE_EN.search(text) or "?" in text:
        return "pending"
    return "unknown"


def _confidence(
    classification: Classification,
    has_times: bool,
    has_duration: bool,
    has_timezone: bool,
    has_link: bool,
) -> float:
    score = 0.0
    if classification != "other":
        score += 0.3
    if has_times:
        score += 0.25
    if has_duration:
        score += 0.15
    if has_timezone:
        score += 0.15
    if has_link:
        score += 0.1
    if classification == "other" and not (has_times or has_duration):
        score = min(score + 0.2, 0.5)
    return min(score + 0.05, 1.0)


class EmailExtractor:
    def __init__(self, model_name: str = "fr_core_news_sm") -> None:
        self._model_name = model_name
        self._nlp = None

    @property
    def nlp(self):
        if self._nlp is None:
            self._nlp = _load_nlp(self._model_name)
        return self._nlp

    def extract(self, email: EmailInput) -> ExtractionResult:
        text = f"{email.subject}\n{email.body}".strip()
        if not text:
            return ExtractionResult(classification="other", confidence=0.0)

        classification = _classify(text)
        proposed_times = _extract_times(text)
        duration_minutes = _extract_duration_minutes(text)
        timezone = _extract_timezone(text)
        meeting_link = _extract_meeting_link(text)
        modality = _extract_modality(text)
        participants = _extract_participants(text)
        organizer = participants[0] if participants else None
        thread_status = _thread_status(text)

        needs_clarification = (
            classification == "meeting_schedule"
            and (timezone is None or duration_minutes is None)
        )

        confidence = _confidence(
            classification,
            has_times=len(proposed_times) > 0,
            has_duration=duration_minutes is not None,
            has_timezone=timezone is not None,
            has_link=meeting_link is not None,
        )

        return ExtractionResult(
            classification=classification,
            proposed_times=proposed_times,
            duration_minutes=duration_minutes,
            timezone=timezone,
            modality=modality,
            meeting_link=meeting_link,
            participants=participants,
            organizer=organizer,
            constraints=[],
            thread_status=thread_status,
            needs_clarification=needs_clarification,
            confidence=confidence,
        )
