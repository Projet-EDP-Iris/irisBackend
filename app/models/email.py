from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.models.base import Base  # Fix: was circular import via app.models


class Email(Base):
    __tablename__ = "emails"

    # Identifiants techniques
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Contenu brut de l'email
    subject = Column(String)
    body = Column(Text)
    sender = Column(String, nullable=True)
    received_at = Column(DateTime, server_default=func.now())

    # Etape 1 : Detection & Extraction
    extraction_data = Column(JSON, nullable=True)
    summary = Column(Text, nullable=True)

    # Etape 2 : Planification (Les creneaux suggeres)
    predicted_slots = Column(JSON, nullable=True)

    # Etape 3 : Suggestion (Le texte final genere pour la reponse)
    generated_suggestion = Column(Text, nullable=True)

    # Statut pour le suivi du workflow
    status = Column(String, default="pending")

    # Calendar integration
    calendar_event_id = Column(String, nullable=True)
    calendar_event_ids = Column(JSON, nullable=True)
