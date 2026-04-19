from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.sql import func
from app.models import Base  # Importation de la base de données de Danlyn

class Email(Base):
    __tablename__ = "emails"

    # Identifiants techniques
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, index=True) # ID unique venant de Gmail
    user_id = Column(Integer, ForeignKey("users.id")) # Lien avec l'utilisateur
    
    # Contenu brut de l'email
    subject = Column(String)
    body = Column(Text)
    sender = Column(String, nullable=True)
    received_at = Column(DateTime, server_default=func.now())

    # --- RÉSULTATS DE L'IA (Ton pipeline technique) ---
    
    # Étape 1 : Détection & Extraction
    # On stocke l'objet complet ici pour que la prédiction puisse le lire
    extraction_data = Column(JSON, nullable=True) 
    summary = Column(Text, nullable=True) 
    
    # Étape 2 : Planification (Les créneaux suggérés)
    # Stocké en JSON pour garder la structure de liste [{start, end}, ...]
    predicted_slots = Column(JSON, nullable=True) 
    
    # Étape 3 : Suggestion (Le texte final généré pour la réponse)
    generated_suggestion = Column(Text, nullable=True)

    # Statut pour le suivi du workflow
    status = Column(String, default="pending") # pending, detected, predicted, completed