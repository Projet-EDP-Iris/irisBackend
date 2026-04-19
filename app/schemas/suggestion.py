
from pydantic import BaseModel


class SuggestionResponse(BaseModel):
    email_id: int
    suggested_content: str
    status: str = "READY"

class SuggestionCreate(BaseModel):

    tone: str | None = "professional"
