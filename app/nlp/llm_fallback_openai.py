import json

from app.core.config import settings
from app.schemas.detection import (
    EmailInput,
    ExtractionResult,
    Participant,
    TimeWindow,
)


def _merge_patch(partial: ExtractionResult, patch: dict) -> ExtractionResult:
    data = partial.model_dump()
    for key, value in patch.items():
        if value is None:
            continue
        if key not in data:
            continue
        current = data[key]
        if current is None or (isinstance(current, list) and len(current) == 0):
            if key == "proposed_times" and isinstance(value, list):
                data[key] = [TimeWindow(**t) if isinstance(t, dict) else t for t in value]
            elif key == "organizer" and isinstance(value, dict):
                data[key] = Participant(**value)
            elif key == "participants" and isinstance(value, list):
                data[key] = [Participant(**p) if isinstance(p, dict) else p for p in value]
            else:
                data[key] = value
    merged = ExtractionResult(**data)
    merged.confidence = min(partial.confidence + 0.2, 1.0)
    merged.needs_clarification = (
        merged.classification == "meeting_schedule"
        and (merged.timezone is None or merged.duration_minutes is None)
    )
    return merged


class LLMFallbackOpenAI:
    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None and settings.OPENAI_API_KEY:
            from openai import OpenAI
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    def enhance(self, email: EmailInput, partial: ExtractionResult) -> ExtractionResult:
        if partial.confidence >= settings.LLM_CONFIDENCE_THRESHOLD:
            return partial
        if not settings.OPENAI_API_KEY or not self.client:
            return partial
        try:
            schema = {
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_patch",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string"},
                            "duration_minutes": {"type": "integer"},
                            "proposed_times": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "start": {"type": "string"},
                                        "end": {"type": "string"},
                                        "timezone": {"type": "string"},
                                    },
                                },
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            }
            prompt = (
                "From this email, extract ONLY missing scheduling fields. "
                "Return a JSON object with only the fields you can fill: timezone, duration_minutes, proposed_times (list of {start, end, timezone}). "
                "Do not include fields that are already clear or that you cannot infer.\n\n"
                f"Subject: {email.subject[:200]}\nBody: {email.body[:1500]}"
            )
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                response_format=schema,
            )
            content = resp.choices[0].message.content
            if not content:
                return partial
            patch = json.loads(content)
            if not isinstance(patch, dict):
                return partial
            return _merge_patch(partial, patch)
        except Exception:
            return partial
