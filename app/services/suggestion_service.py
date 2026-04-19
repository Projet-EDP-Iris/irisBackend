def generate_email_suggestion(email_content: str, slots: list) -> str:
    """
    Prend le contenu d'un email et les créneaux trouvés pour rédiger une réponse.
    """
    # 1. On prépare la liste des créneaux en texte lisible
    formatted_slots = ""
    for slot in slots:
        start = slot.get('start', 'N/A')
        formatted_slots += f"- {start}\n"

    # 2. Simulation de la rédaction 
    prompt_simule = (
        f"Bonjour,\n\n"
        f"Merci pour votre message concernant : '{email_content[:50]}...'.\n"
        f"Je serais ravi d'en discuter avec vous. Voici mes disponibilités :\n"
        f"{formatted_slots}\n"
        f"Dites-moi ce qui vous convient le mieux.\n\n"
        f"Cordialement,\nIris AI"
    )
    
    return prompt_simule