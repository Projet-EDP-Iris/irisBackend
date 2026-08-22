from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.models.base import Base  # Fix: was circular import via app.models


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_emails_message_id_user"),
    )

    # Identifiants techniques
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String, index=True)
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

    # Email metadata persisted from provider
    email_date = Column(String(100), nullable=True)   # Date header value from the email
    category = Column(String(20), nullable=True)       # UI tab: rdv|action|attente|bonsplans|info
    provider = Column(String(20), nullable=True)       # "gmail" | "outlook"

    # Calendar integration
    calendar_event_id = Column(String, nullable=True)
    calendar_event_ids = Column(JSON, nullable=True)

    # RFC 2822 Message-ID header — used for email threading (In-Reply-To / References)
    rfc_message_id = Column(String, nullable=True)

    # Terminal-state flag shared by all categories (see app/api/endpoints/processing_state.py
    # for how it feeds processed_by_category, and calendar.py / emails.py for what sets it).
    is_done = Column(Boolean, default=False, nullable=False, server_default="0")

    # "User has opened this email" — distinct from is_done (a category-specific terminal
    # action). Drives the frontend's "Lu" badge; set once via POST /emails/{id}/mark-read.
    is_read = Column(Boolean, default=False, nullable=False, server_default="0")
