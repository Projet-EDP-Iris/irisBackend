"""
Two-layer email classification pipeline.

Layer 1 — Regex (fast, deterministic):
  Ordered regex patterns cover the six categories below in priority order.
  A match short-circuits further evaluation. Confidence scores reflect how
  strongly the pattern signals the category (0.65 – 0.9).

  Priority order (highest to lowest):
    meeting_cancel  → CANCEL_EN     (0.9)
    meeting_reschedule → RESCHEDULE_EN (0.85)
    meeting_schedule   → SCHEDULE_EN   (0.8)
    bonsplans          → BONSPLANS_RE  (0.75)
    attente            → ATTENTE_RE    (0.7)
    action             → ACTION_RE     (0.7)
    info               → INFO_RE       (0.65)

Layer 2 — spaCy NER + morphology (slower, handles edge cases):
  Runs only when no regex matched. Inspects the first 600 characters for
  named entities, imperative verb moods, and question density to make a
  lower-confidence classification (0.3 – 0.6).

  Fallback when spaCy is unavailable or raises: returns ("info", 0.3).

After classification, meeting-type emails extract additional metadata
(proposed times via dateparser, duration, timezone, meeting link, modality,
participants). Non-meeting emails skip this step for performance.

Frontend mapping: classification_to_category() maps the seven internal values
to the five UI tab IDs: rdv / action / attente / bonsplans / info.
"""
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
    r"\b(meeting|appointment|réunion|"
    r"(?:prendre?|fixer|planifier|notre|votre|un)\s+rendez-vous|"
    r"rendez-vous\s+(?:le\s+\d|à\s+\d{1,2}[h:]|avec|prévu|confirmé|téléphonique)|"
    r"schedule\s+a\s+(?:call|meeting|time|sync)|"
    r"book\s+a\s+(?:call|meeting|slot|time)|"
    r"set\s+up\s+a\s+(?:call|meeting|time|sync)|find\s+a\s+time|"
    r"hop\s+on\s+a\s+(?:call|zoom|teams|meet)|let.s\s+(?:meet|chat|sync|catch\s+up)|"
    r"meet\s+(?:on|at|up)|catch[\s-]?up|"
    r"call\s+(?:at|on|scheduled|tomorrow|next\s+week)|"
    r"quick\s+(?:call|chat|sync)|petit\s+(?:appel|point|call)|call\s+rapide|"
    r"on\s+se\s+retrouve|faire\s+(?:un|le)\s+point|point\s+de\s+(?:situation|suivi)|"
    r"sync(?:hronisation)?|convocation|invitation\s+(?:à\s+la\s+)?réunion|"
    r"coffee\s+chat|virtual\s+coffee|grab\s+a\s+coffee|"
    r"(?:lundi|mardi|mercredi|jeudi|vendredi)\s+(?:prochain|à\s+\d{1,2}[h:]\d{0,2}|\d{1,2}[h:]\d{0,2}|matin|soir|après-midi|midi)|"
    r"(?:monday|tuesday|wednesday|thursday|friday)\s+(?:at\s+\d{1,2}|next|morning|afternoon|evening)|"
    r"dispo\s+(?:lundi|mardi|mercredi|jeudi|vendredi|ce\s+soir|demain|la\s+semaine)|"
    r"tu\s+es\s+(?:dispo|libre|disponible)|"
    r"vous\s+êtes\s+(?:dispo|libre|disponible)|"
    r"on\s+se\s+voit\s+(?:quand|demain|lundi|mardi|mercredi|jeudi|vendredi)|"
    r"ça\s+te\s+va\s+(?:lundi|mardi|mercredi|jeudi|vendredi|pour|demain)|"
    r"libre\s+(?:lundi|mardi|mercredi|jeudi|vendredi|demain|ce\s+soir)|"
    r"are\s+you\s+(?:free|available)\s+(?:on|this|next)|"
    r"(?:free|available)\s+(?:monday|tuesday|wednesday|thursday|friday|tomorrow))\b",
    re.IGNORECASE,
)
CANCEL_EN = re.compile(
    r"\b(cancel|cancelled|cancellation|annul|annulé|annulation|postpone|reporté|"
    r"call off|won.t happen|"
    r"ne pourra pas\s+(?:avoir lieu|se tenir|être maintenu|y participer))\b",
    re.IGNORECASE,
)
RESCHEDULE_EN = re.compile(
    r"\b(reschedule|déplacer\s+(?:notre|le|la|un)|reporter\s+(?:notre|le|la|un|à)|"
    r"new\s+time|nouvelle\s+date|change\s+of\s+time|changer\s+(?:l.heure|la\s+date))\b",
    re.IGNORECASE,
)
BONSPLANS_RE = re.compile(
    r"\b(promo|promotion|offre\s+sp[eé]ciale|offre\s+exclusive|bon\s+plan|r[eé]duction|rabais|soldes?|"
    r"vente\s+priv[eé]e|flash\s+sale|deal|discount|coupon|code\s+promo|voucher|"
    r"uber\s*eats|deliveroo|just\s*eat|\d{1,3}\s*%\s*off|\d{1,3}\s*%\s*de\s*r[eé]duction|"
    r"jusqu.[àa]\s+\d{1,3}\s*%|[eé]conomisez|cashback|livraison\s+offerte|"
    r"gratuit|free\s+trial|essai\s+gratuit|limited\s+time|offre\s+limit[eé]e|"
    r"valable\s+jusqu|points?\s+fid[eé]lit[eé]|membres?\s+exclusifs?|r[eé]compenses?|"
    r"save\s+\d+|special\s+offer|exclusive\s+offer|"
    r"black\s+friday|cyber\s+monday|prime\s+day|nos\s+offres)\b",
    re.IGNORECASE,
)
ATTENTE_RE = re.compile(
    r"\b(follow[- ]?up|relance|en\s+attente\s+de|waiting\s+for\s+your|"
    r"j.attends\s+(?:votre|ta)|I.m\s+waiting|haven.t\s+heard|toujours\s+en\s+attente|"
    r"still\s+waiting|awaiting\s+your|pending\s+your|dans\s+l.attente\s+de|"
    r"avez-vous\s+eu\s+le\s+temps|did\s+you\s+have\s+a\s+chance|any\s+update|"
    r"sans\s+nouvelles?\s+de|juste\s+pour\s+v[eé]rifier|tu\s+as\s+vu\s+mon|"
    r"est-ce\s+que\s+tu\s+peux\s+confirmer|me\s+permets?\s+de\s+(?:te\s+)?relancer|"
    r"un\s+petit\s+rappel|reminder|pas\s+encore\s+re[cç]u|sans\s+r[eé]ponse|"
    r"not\s+yet\s+received|just\s+a\s+reminder|checking\s+in)\b",
    re.IGNORECASE,
)
ACTION_RE = re.compile(
    r"\b(action\s+required|action\s+needed|urgent|asap|d[eè]s\s+que\s+possible|"
    r"merci\s+de\s+(?:bien\s+vouloir|r[eé]pondre|confirmer|valider|envoyer)|"
    r"please\s+(?:reply|respond|confirm|review|sign|approve|send|fill|complete|provide)|"
    r"pouvez-vous|pourriez-vous|could\s+you|would\s+you\s+(?:mind|please)|"
    r"je\s+vous\s+(?:demande|sollicite|prie)|your\s+(?:approval|signature|feedback|input)|"
    r"deadline|[àa]\s+faire|[àa]\s+valider|[àa]\s+signer|[àa]\s+retourner|[àa]\s+compl[eé]ter|"
    r"r[eé]pondez\s+avant|respond\s+by|due\s+(?:date|by|on)|"
    r"formulaire\s+[àa]\s+remplir|veuillez\s+(?:remplir|confirmer|valider|signer|envoyer|noter)|"
    r"n.oubliez\s+pas\s+de|action\s+de\s+(?:ta|votre)\s+part|"
    r"besoin\s+de\s+(?:ta|votre)\s+r[eé]ponse|update\s+required|must\s+be\s+(?:done|completed)|"
    r"document\s+[àa]\s+signer|avant\s+le\s+\d)\b",
    re.IGNORECASE,
)
INFO_RE = re.compile(
    r"\b(newsletter|bulletin\s+(?:d.information|mensuel|hebdomadaire)|"
    r"rapport\s+(?:mensuel|hebdomadaire|annuel|de\s+suivi|d.activit[eé])|"
    r"compte[\s-]rendu|r[eé]sum[eé]\s+(?:de\s+la\s+semaine|du\s+mois|de\s+r[eé]union)|"
    r"mise\s+[àa]\s+jour\s+(?:du\s+projet|de\s+la\s+situation)|note\s+interne|"
    r"pour\s+(?:votre\s+)?information|FYI|for\s+your\s+(?:information|records)|"
    r"ci-joint\s+(?:le|la|les|notre|votre)|veuillez\s+trouver\s+ci-joint|"
    r"digest\s+(?:de|du)|weekly\s+(?:digest|update|summary)|monthly\s+(?:report|summary)|"
    r"no\s+action\s+(?:required|needed)|aucune\s+action\s+(?:requise|n[eé]cessaire)|"
    r"à\s+titre\s+d.information)\b",
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

# Platform-specific video conferencing URL patterns — ordered highest to lowest specificity.
# The first pattern that matches wins, so more precise patterns come first.
_PLATFORM_LINKS: list[tuple[str, re.Pattern[str]]] = [
    ("zoom",   re.compile(r"https?://(?:[\w-]+\.)?zoom\.us/(?:j|my)/[\w?&=%+.-]+")),
    ("teams",  re.compile(r"https?://teams\.microsoft\.com/l/meetup-join/[^\s<>]+")),
    ("meet",   re.compile(r"https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}")),
    ("webex",  re.compile(r"https?://(?:[\w-]+\.)?webex\.com/(?:meet|join)/[^\s<>]+")),
]

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


def _classify_with_spacy(text: str, nlp) -> tuple[str, float]:
    """Layer 2: spaCy NER + morphology for emails that didn't match any regex."""
    doc = nlp(text[:600])
    ent_labels = {ent.label_ for ent in doc.ents}
    sentences = list(doc.sents)

    has_imperative = any(
        "Imp" in token.morph.get("Mood", [])
        for token in doc if token.pos_ == "VERB"
    )
    question_ratio = (
        sum(1 for s in sentences if "?" in s.text) / max(len(sentences), 1)
    )
    has_location = "LOC" in ent_labels
    has_org = "ORG" in ent_labels

    if has_imperative:
        return "action", 0.6
    if question_ratio >= 0.3:
        return "attente", 0.55
    if has_org and not has_location:
        return "info", 0.45
    return "info", 0.3


def _classify(text: str, nlp=None) -> tuple[Classification, float]:
    # Layer 1: Regex — fast, high-confidence keyword matching
    if CANCEL_EN.search(text):
        return "meeting_cancel", 0.9
    if RESCHEDULE_EN.search(text):
        return "meeting_reschedule", 0.85
    if SCHEDULE_EN.search(text):
        return "meeting_schedule", 0.8
    if BONSPLANS_RE.search(text):
        return "bonsplans", 0.75
    if ATTENTE_RE.search(text):
        return "attente", 0.7
    if ACTION_RE.search(text):
        return "action", 0.7
    if INFO_RE.search(text):
        return "info", 0.65
    # Layer 2: spaCy NER + morphology for remaining emails
    if nlp is not None:
        try:
            return _classify_with_spacy(text, nlp)
        except Exception:
            pass
    return "info", 0.3


def classification_to_category(classification: str) -> str:
    """Map NLP Classification value to frontend UI tab ID."""
    if classification in ("meeting_schedule", "meeting_cancel", "meeting_reschedule"):
        return "rdv"
    if classification in ("action", "attente", "bonsplans", "info"):
        return classification
    return "info"  # covers "other" and any unknown future value


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


def _extract_meeting_link(text: str) -> tuple[str | None, str | None]:
    """Return (url, platform) where platform is 'zoom'|'teams'|'meet'|'webex'|None.

    Platform-specific patterns take priority over generic URL matching so that
    a Zoom join link is preferred over an arbitrary https URL in the same email.
    """
    for platform, pattern in _PLATFORM_LINKS:
        m = pattern.search(text)
        if m:
            return m.group(0), platform
    m = LINK_RE.search(text)
    return (m.group(0), None) if m else (None, None)


def _extract_modality(text: str, link_platform: str | None = None) -> str | None:
    """Return video-call platform name, preferring the link-derived platform."""
    if link_platform:
        return link_platform
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
    base_conf: float = 0.0,
) -> float:
    score = base_conf
    meeting_types = ("meeting_schedule", "meeting_cancel", "meeting_reschedule")
    non_meeting_categories = ("action", "attente", "bonsplans")
    if classification in meeting_types:
        score += 0.3
    elif classification in non_meeting_categories:
        score += 0.2
    if has_times:
        score += 0.25
    if has_duration:
        score += 0.15
    if has_timezone:
        score += 0.15
    if has_link:
        score += 0.1
    if classification in ("other", "info") and not (has_times or has_duration):
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
            return ExtractionResult(classification="info", confidence=0.0)

        classification, base_conf = _classify(text, self.nlp)
        _meeting_types = ("meeting_schedule", "meeting_cancel", "meeting_reschedule")
        proposed_times = _extract_times(text) if classification in _meeting_types else []
        duration_minutes = _extract_duration_minutes(text) if classification in _meeting_types else None
        timezone = _extract_timezone(text)
        meeting_link, link_platform = _extract_meeting_link(text)
        modality = _extract_modality(text, link_platform)
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
            base_conf=base_conf,
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
