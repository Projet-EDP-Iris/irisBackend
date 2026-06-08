import asyncio
import random


async def generate_mail_suggestions(summary: str):
    """Return three mock reply variants for the given email summary."""
    await asyncio.sleep(0.8)

    templates = [
        {
            "amical": f"Hey! Works for me regarding {summary}. How do you want to organise it?",
            "formel": f"Dear Sir/Madam, I acknowledge your message regarding {summary}. I will follow up with a concrete proposal.",
            "court": "Got it. Let's do that!"
        },
        {
            "amical": f"Hi! Great idea about {summary}. I'm available if you'd like to discuss.",
            "formel": f"Dear Sir/Madam, further to our exchange on {summary}, I confirm my agreement to proceed.",
            "court": "Noted, thanks."
        }
    ]

    chosen = random.choice(templates)

    return [
        {"label": "Amical", "content": chosen["amical"]},
        {"label": "Formel", "content": chosen["formel"]},
        {"label": "Court", "content": chosen["court"]}
    ]
