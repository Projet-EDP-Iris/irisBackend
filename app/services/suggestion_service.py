def generate_email_suggestion(email_content: str, slots: list) -> str:
    """Generate a reply draft given the email content and a list of proposed slots."""
    formatted_slots = ""
    for slot in slots:
        start = slot.get('start', 'N/A')
        formatted_slots += f"- {start}\n"

    return (
        f"Hello,\n\n"
        f"Thank you for your message regarding: '{email_content[:50]}...'.\n"
        f"I would be happy to discuss this with you. Here are my available slots:\n"
        f"{formatted_slots}\n"
        f"Please let me know which time works best for you.\n\n"
        f"Best regards,\nIris AI"
    )
