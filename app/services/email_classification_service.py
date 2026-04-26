from app.services.gmail_service import fetch_recent_emails_as_inputs_for_user
from app.ML.classifier import classify_email

def fetch_and_classify_emails(user_id: int, n: int = 10):
    emails = fetch_recent_emails_as_inputs_for_user(user_id, n=n)
    results = []

    for email in emails:
        category = classify_email(email.subject, email.body)
        results.append({
            "subject": email.subject,
            "body": email.body,
            "message_id": email.message_id,
            "category": category
        })

    return results
