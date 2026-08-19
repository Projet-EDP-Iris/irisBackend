from datetime import datetime

from pydantic import BaseModel


class ProcessingStateResponse(BaseModel):
    user_id: int
    is_active: bool
    total_emails: int
    processed_emails: int
    processed_by_category: dict[str, dict[str, int]]
    updated_at: datetime

    class Config:
        from_attributes = True
