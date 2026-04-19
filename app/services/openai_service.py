import asyncio
import random


async def generate_mail_suggestions(summary: str):
    """
    VERSION TEST (MOCK) : Simule l'appel à GPT-5.4 Mini.
    Permet de tester le Frontend et le Backend sans clé API.
    """
    # On simule un petit délai réseau de 0.8 seconde pour faire "vrai" lors de la démo
    await asyncio.sleep(0.8)

    # Liste de templates pour varier un peu les tests
    templates = [
        {
            "amical": f"Coucou ! Pour {summary}, ça me va carrément. On s'organise comment ?",
            "formel": f"Bonjour, j'accuse réception de votre message concernant {summary}. Je reviens vers vous avec une proposition concrète.",
            "court": "Bien reçu. On fait comme ça !"
        },
        {
            "amical": f"Salut ! Super idée pour {summary}. Je suis dispo si tu veux en parler.",
            "formel": f"Madame, Monsieur, suite à notre échange sur {summary}, je vous confirme mon accord pour la suite des opérations.",
            "court": "C'est noté, merci."
        }
    ]

    # On choisit un set de réponses au hasard
    chosen = random.choice(templates)

    return [
        {"label": "Amical", "content": chosen["amical"]},
        {"label": "Formel", "content": chosen["formel"]},
        {"label": "Court", "content": chosen["court"]}
    ]
