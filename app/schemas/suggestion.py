from pydantic import BaseModel
from typing import Optional

class SuggestionResponse(BaseModel):
    email_id: int
    suggested_content: str 
    status: str = "READY"

class SuggestionCreate(BaseModel):
    
    tone: Optional[str] = "professional"