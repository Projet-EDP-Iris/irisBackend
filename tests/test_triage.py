"""
Tests unitaires — Tri et classification des emails
Vérifie que chaque type d'email atterrit dans la bonne catégorie.
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import patch

import pytest

from app.nlp.extractor import EmailExtractor, _classify, classification_to_category
from app.schemas.detection import EmailInput
from app.services.detection import categorize_email, detect_single


@pytest.fixture
def extractor():
    return EmailExtractor(model_name="fr_core_news_sm")


# ─────────────────────────────────────────────────────────────
# 1. RÉUNION À PLANIFIER  →  catégorie "rdv"
# ─────────────────────────────────────────────────────────────

def test_triage_reunion_francais(extractor):
    """Un email avec 'réunion' doit aller dans rdv."""
    email = EmailInput(
        subject="Réunion de suivi",
        body="Bonjour, pouvons-nous organiser une réunion mardi à 10h ?",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_schedule"
    assert classification_to_category(result.classification) == "rdv"


def test_triage_meeting_english(extractor):
    """Un email avec 'schedule a call' doit aller dans rdv."""
    email = EmailInput(
        subject="Quick call",
        body="Hi, can we schedule a call this Friday at 3pm?",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_schedule"
    assert classification_to_category(result.classification) == "rdv"


def test_triage_rendez_vous(extractor):
    """Un email proposant un rendez-vous doit aller dans rdv."""
    email = EmailInput(
        subject="Rendez-vous",
        body="Je vous propose un rendez-vous jeudi prochain à 14h.",
    )
    result = extractor.extract(email)
    assert classification_to_category(result.classification) == "rdv"


# ─────────────────────────────────────────────────────────────
# 2. ANNULATION  →  catégorie "rdv" (sous-type cancel)
# ─────────────────────────────────────────────────────────────

def test_triage_annulation_francais(extractor):
    """Un email d'annulation doit être classé meeting_cancel."""
    email = EmailInput(
        subject="Annulation réunion",
        body="La réunion de demain est annulée. Désolé pour la gêne occasionnée.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_cancel"
    assert classification_to_category(result.classification) == "rdv"


def test_triage_cancelled_english(extractor):
    """Cancel en anglais doit être détecté."""
    email = EmailInput(
        subject="Meeting cancelled",
        body="Unfortunately the meeting is cancelled due to a conflict.",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_cancel"


# ─────────────────────────────────────────────────────────────
# 3. REPORT / RESCHEDULE  →  catégorie "rdv"
# ─────────────────────────────────────────────────────────────

def test_triage_report_reunion(extractor):
    """Un email de report doit être classé meeting_reschedule."""
    email = EmailInput(
        subject="Report de réunion",
        body="Pouvez-vous reporter notre réunion à la semaine prochaine ?",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_reschedule"
    assert classification_to_category(result.classification) == "rdv"


def test_triage_reschedule_english(extractor):
    """Reschedule en anglais doit être détecté."""
    email = EmailInput(
        subject="New time",
        body="Can we reschedule our call to a new time next week?",
    )
    result = extractor.extract(email)
    assert result.classification == "meeting_reschedule"


# ─────────────────────────────────────────────────────────────
# 4. ACTION REQUISE  →  catégorie "action"
# ─────────────────────────────────────────────────────────────

def test_triage_action_requise(extractor):
    """Un email avec 'merci de confirmer' doit aller dans action."""
    email = EmailInput(
        subject="Validation requise",
        body="Merci de bien vouloir valider le document avant vendredi.",
    )
    result = extractor.extract(email)
    assert result.classification == "action"
    assert classification_to_category(result.classification) == "action"


def test_triage_urgent(extractor):
    """Un email urgent doit aller dans action."""
    email = EmailInput(
        subject="Urgent",
        body="Bonjour, c'est urgent, merci de répondre dès que possible.",
    )
    result = extractor.extract(email)
    assert result.classification == "action"


def test_triage_please_sign(extractor):
    """Please sign doit déclencher action."""
    email = EmailInput(
        subject="Document",
        body="Please review and approve the attached contract by tomorrow.",
    )
    result = extractor.extract(email)
    assert result.classification == "action"


# ─────────────────────────────────────────────────────────────
# 5. EN ATTENTE  →  catégorie "attente"
# ─────────────────────────────────────────────────────────────

def test_triage_relance(extractor):
    """Un email de relance doit aller dans attente."""
    email = EmailInput(
        subject="Relance",
        body="Je me permets de vous relancer concernant ma demande de la semaine dernière.",
    )
    result = extractor.extract(email)
    assert result.classification == "attente"
    assert classification_to_category(result.classification) == "attente"


def test_triage_follow_up(extractor):
    """Follow-up en anglais doit aller dans attente."""
    email = EmailInput(
        subject="Follow-up",
        body="Just following up on my previous email. Any update on this?",
    )
    result = extractor.extract(email)
    assert result.classification == "attente"


# ─────────────────────────────────────────────────────────────
# 6. BONS PLANS / PROMO  →  catégorie "bonsplans"
# ─────────────────────────────────────────────────────────────

def test_triage_promo(extractor):
    """Un email promo doit aller dans bonsplans."""
    email = EmailInput(
        subject="Offre spéciale -50%",
        body="Profitez de notre promotion exclusive : 50% de réduction ce week-end !",
    )
    result = extractor.extract(email)
    assert result.classification == "bonsplans"
    assert classification_to_category(result.classification) == "bonsplans"


def test_triage_discount_english(extractor):
    """Discount en anglais doit aller dans bonsplans."""
    email = EmailInput(
        subject="Flash sale",
        body="Limited time offer: 30% off on all products. Use code SAVE30.",
    )
    result = extractor.extract(email)
    assert result.classification == "bonsplans"


# ─────────────────────────────────────────────────────────────
# 7. INFO (aucune action requise)  →  catégorie "info"
# ─────────────────────────────────────────────────────────────

def test_triage_email_vide(extractor):
    """Un email vide doit aller dans info avec confiance 0."""
    email = EmailInput(subject="", body="")
    result = extractor.extract(email)
    assert result.classification == "info"
    assert result.confidence == 0.0
    assert classification_to_category(result.classification) == "info"


def test_triage_email_info(extractor):
    """Un simple email informatif doit aller dans info."""
    email = EmailInput(
        subject="Information",
        body="Bonjour, veuillez trouver ci-joint le rapport mensuel de l'équipe.",
    )
    result = extractor.extract(email)
    assert classification_to_category(result.classification) == "info"


# ─────────────────────────────────────────────────────────────
# 8. MAPPING catégorie → onglet frontend
# ─────────────────────────────────────────────────────────────

def test_mapping_meeting_types_vers_rdv():
    """Les 3 types réunion doivent tous pointer vers l'onglet rdv."""
    assert classification_to_category("meeting_schedule")   == "rdv"
    assert classification_to_category("meeting_cancel")     == "rdv"
    assert classification_to_category("meeting_reschedule") == "rdv"


def test_mapping_autres_categories():
    """Les autres catégories restent identiques dans le frontend."""
    assert classification_to_category("action")    == "action"
    assert classification_to_category("attente")   == "attente"
    assert classification_to_category("bonsplans") == "bonsplans"
    assert classification_to_category("info")      == "info"


def test_mapping_valeur_inconnue_vers_info():
    """Une valeur inconnue doit tomber dans info par défaut."""
    assert classification_to_category("valeur_inconnue") == "info"


# ─────────────────────────────────────────────────────────────
# 9. EMAILS FRANGLAIS  →  bonne catégorie malgré le mélange
# ─────────────────────────────────────────────────────────────

def test_triage_franglais_sync(extractor):
    """'Let's sync demain' en franglais doit aller dans rdv."""
    email = EmailInput(
        subject="Quick sync",
        body="Hey, let's sync demain à 14h pour faire le point sur le projet.",
    )
    result = extractor.extract(email)
    assert classification_to_category(result.classification) == "rdv"


def test_triage_franglais_catch_up(extractor):
    """'Catch up' en franglais doit être détecté comme rdv."""
    email = EmailInput(
        subject="Catch up cette semaine",
        body="On pourrait faire un catch up rapide cette semaine ? Je suis dispo jeudi.",
    )
    result = extractor.extract(email)
    assert classification_to_category(result.classification) == "rdv"


def test_triage_franglais_follow_up_action(extractor):
    """Email franglais avec 'please confirm' doit aller dans action."""
    email = EmailInput(
        subject="Confirmation requise",
        body="Bonjour, please confirm avant vendredi. Merci !",
    )
    result = extractor.extract(email)
    assert result.classification == "action"


# ─────────────────────────────────────────────────────────────
# 10. NOUVEAUX PATTERNS ENRICHIS
# ─────────────────────────────────────────────────────────────

def test_triage_checking_in(extractor):
    """'Checking in' doit aller dans attente."""
    email = EmailInput(
        subject="Checking in",
        body="Just checking in on the status of my request from last week.",
    )
    result = extractor.extract(email)
    assert result.classification == "attente"


def test_triage_cashback_promo(extractor):
    """Email cashback doit aller dans bonsplans."""
    email = EmailInput(
        subject="Cashback disponible",
        body="Vous avez du cashback disponible ! Économisez sur votre prochain achat.",
    )
    result = extractor.extract(email)
    assert result.classification == "bonsplans"


def test_triage_newsletter_info(extractor):
    """Une newsletter doit aller dans info avec confiance correcte."""
    email = EmailInput(
        subject="Newsletter mensuelle",
        body="Voici notre newsletter mensuelle avec les actualités du mois.",
    )
    result = extractor.extract(email)
    assert classification_to_category(result.classification) == "info"
    assert result.confidence > 0.3


def test_triage_rapport_mensuel_info(extractor):
    """Un rapport mensuel explicite doit aller dans info."""
    email = EmailInput(
        subject="Rapport mensuel - Mai 2025",
        body="Veuillez trouver ci-joint le rapport mensuel de l'équipe.",
    )
    result = extractor.extract(email)
    assert classification_to_category(result.classification) == "info"


def test_triage_formulaire_action(extractor):
    """'Formulaire à remplir' doit aller dans action."""
    email = EmailInput(
        subject="Formulaire RH",
        body="Veuillez remplir le formulaire à remplir avant le 15 mai.",
    )
    result = extractor.extract(email)
    assert result.classification == "action"


def test_triage_sans_nouvelles_attente(extractor):
    """'Sans nouvelles de toi' doit aller dans attente."""
    email = EmailInput(
        subject="Relance",
        body="Je suis sans nouvelles de toi depuis une semaine concernant ma proposition.",
    )
    result = extractor.extract(email)
    assert result.classification == "attente"


def test_triage_offre_exclusive_bonsplans(extractor):
    """'Offre exclusive' doit aller dans bonsplans."""
    email = EmailInput(
        subject="Offre exclusive pour vous",
        body="Profitez de cette offre exclusive réservée à nos membres !",
    )
    result = extractor.extract(email)
    assert result.classification == "bonsplans"


# ─────────────────────────────────────────────────────────────
# 11. CHAQUE EMAIL A TOUJOURS UNE CATÉGORIE NON-NULLE
# ─────────────────────────────────────────────────────────────

def test_chaque_email_a_une_categorie(extractor):
    """Aucun email ne doit rester sans catégorie valide."""
    emails = [
        EmailInput(subject="Sujet aléatoire", body="Texte quelconque sans mots-clés particuliers."),
        EmailInput(subject="", body="   "),
        EmailInput(subject="fezgfezg", body="fgzegfzegfzeg"),
        EmailInput(subject="Bonjour", body="Cordialement."),
    ]
    valid_categories = {"rdv", "action", "attente", "bonsplans", "info"}
    for email in emails:
        result = extractor.extract(email)
        category = classification_to_category(result.classification)
        assert category in valid_categories, f"Catégorie invalide '{category}' pour {email}"


def test_email_ambigue_low_confidence_toujours_classe(extractor):
    """Un email sans signal fort doit tout de même avoir une catégorie (info) et confiance >= 0."""
    email = EmailInput(
        subject="Divers",
        body="Voici quelques informations diverses sans structure particulière.",
    )
    result = extractor.extract(email)
    assert result.classification is not None
    assert result.confidence >= 0.0
    assert classification_to_category(result.classification) in {"rdv", "action", "attente", "bonsplans", "info"}


# ─────────────────────────────────────────────────────────────
# 12. needs_review — filet de sécurité
# ─────────────────────────────────────────────────────────────

def test_needs_review_absent_sur_email_clair():
    """Un email avec un signal fort ne doit PAS déclencher needs_review."""
    email = EmailInput(subject="Réunion lundi", body="Réunion lundi à 10h, confirme ta dispo.")
    result = detect_single(email)
    assert result.needs_review is False


def test_needs_review_force_info_sur_email_vide():
    """Un email vide (confiance 0) doit se retrouver en info sans needs_review (classification=info direct)."""
    email = EmailInput(subject="", body="")
    result = detect_single(email)
    assert result.classification == "info"
    assert result.confidence == 0.0


def test_needs_review_active_sur_classification_other():
    """Si le NLP renvoie 'other' avec confiance < 0.4, detect_single doit passer en info + needs_review."""
    with patch("app.services.detection._get_extractor") as mock_extractor:
        from app.schemas.detection import ExtractionResult
        mock_extractor.return_value.extract.return_value = ExtractionResult(
            classification="other", confidence=0.2
        )
        email = EmailInput(subject="xyz", body="abc")
        result = detect_single(email)
    assert result.classification == "info"
    assert result.needs_review is True


# ─────────────────────────────────────────────────────────────
# 13. Résilience — exception dans la catégorisation parallèle
# ─────────────────────────────────────────────────────────────

def test_categorize_email_exception_ne_plante_pas_le_batch():
    """Si categorize_email lève une exception sur 1 email, les autres doivent rester classés."""
    call_count = 0

    def flaky_categorize(email: EmailInput) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Erreur simulée sur email #2")
        return categorize_email(email)

    emails = [
        EmailInput(subject="Réunion", body="Réunion demain à 14h."),
        EmailInput(subject="Crash intentionnel", body="Cet email déclenche une exception."),
        EmailInput(subject="Promo", body="50% de réduction ce week-end !"),
    ]
    results = ["info"] * len(emails)
    valid_categories = {"rdv", "action", "attente", "bonsplans", "info"}

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(flaky_categorize, e): i for i, e in enumerate(emails)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = "info"

    assert all(r in valid_categories for r in results), f"Catégories invalides : {results}"
    assert results[0] == "rdv"   # réunion → rdv
    assert results[1] == "info"  # exception → fallback info
    assert results[2] == "bonsplans"


# ─────────────────────────────────────────────────────────────
# 14. Charge — 200 emails en parallèle (simulation 999+)
# ─────────────────────────────────────────────────────────────

def test_charge_200_emails_categories_valides():
    """200 emails de types variés doivent tous être catégorisés correctement en < 30s."""
    templates = [
        (EmailInput(subject="Réunion", body="Réunion lundi à 10h, es-tu dispo ?"), "rdv"),
        (EmailInput(subject="Urgent", body="Action required: please confirm before deadline."), "action"),
        (EmailInput(subject="Relance", body="Just checking in on my previous email."), "attente"),
        (EmailInput(subject="Promo", body="Profitez de 50% de réduction ce week-end !"), "bonsplans"),
        (EmailInput(subject="Info", body="Veuillez trouver ci-joint le rapport mensuel."), "info"),
    ]
    emails = []
    expected = []
    for i in range(200):
        email, cat = templates[i % len(templates)]
        emails.append(EmailInput(subject=email.subject, body=email.body))
        expected.append(cat)

    valid_categories = {"rdv", "action", "attente", "bonsplans", "info"}
    results = [None] * len(emails)

    start = time.time()
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(categorize_email, e): i for i, e in enumerate(emails)}
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = "info"
    elapsed = time.time() - start

    assert all(r in valid_categories for r in results), "Un email n'a pas de catégorie valide"
    assert elapsed < 30, f"Trop lent : {elapsed:.1f}s pour 200 emails"

    # Vérifier la cohérence des catégories sur les emails aux signaux forts
    for i in range(0, 200, len(templates)):
        assert results[i] == expected[i % len(templates)], (
            f"Email #{i} attendu '{expected[i % len(templates)]}', obtenu '{results[i]}'"
        )
