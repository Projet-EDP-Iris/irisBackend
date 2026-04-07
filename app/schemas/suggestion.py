from pydantic import BaseModel
from typing import Optional

class SuggestionResponse(BaseModel):
    email_id: int
    suggested_content: str  # Le corps de l'email rédigé par l'IA
    status: str = "READY"

class SuggestionCreate(BaseModel):
    # Si jamais tu veux passer des instructions spécifiques à l'IA (ex: "sois formel")
    tone: Optional[str] = "professional"