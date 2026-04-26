from pydantic import BaseModel

class EmailIn(BaseModel):
    subject: str
    body: str
