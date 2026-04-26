from fastapi import APIRouter
from app.schemas.email_schema import EmailIn
from app.ML.classifier import classify_email

router = APIRouter(prefix="/emails", tags=["Email Classification"])

@router.post("/classify")
def classify(email: EmailIn):
    category = classify_email(email.subject, email.body)
    return {"category": category}
