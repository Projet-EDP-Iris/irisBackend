import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

print("🚀 Début de l'entraînement du modèle...")

texts = [
    # RDV / Meetings
    "Rendez-vous demain à 14h",
    "Voici le lien pour notre meeting",
    "Merci de confirmer la date",
    "Invitation à une réunion",
    "Calendrier mis à jour pour notre rendez-vous",

    # Action
    "Peux-tu me renvoyer le document",
    "Merci de répondre dès que possible",
    "Action requise : mise à jour du dossier",
    "Peux-tu traiter cette demande",
    "J'ai besoin de ton retour rapidement",

    # En attente / Waiting
    "Je reviens vers toi dès que j'ai une réponse",
    "En attente de validation",
    "Je te tiens au courant quand j'ai du nouveau",
    "Toujours en attente de ton retour",
    "As-tu eu le temps de regarder",

    # Bons plans / Promos
    "Promo Uber Eats -20%",
    "Soldes exceptionnelles chez Amazon",
    "Voici ton code de réduction",
    "Offre spéciale limitée",
    "Promotion sur vos produits préférés",

    # Info / Read
    "Newsletter hebdomadaire",
    "Voici les dernières infos",
    "FYI : mise à jour du service",
    "Informations importantes concernant votre compte",
    "Mise à jour des conditions d'utilisation"
]

labels = [
    "RDV", "RDV", "RDV", "RDV", "RDV",
    "Action", "Action", "Action", "Action", "Action",
    "En attente", "En attente", "En attente", "En attente", "En attente",
    "Bons plans", "Bons plans", "Bons plans", "Bons plans", "Bons plans",
    "Info", "Info", "Info", "Info", "Info"
]

print("📌 Dataset chargé :", len(texts), "exemples")

# ---------------------------------------------------------
# 2. Vectorisation TF-IDF (corrigée)
# ---------------------------------------------------------

vectorizer = TfidfVectorizer(
    lowercase=True,
    max_features=5000,
    stop_words=None  # <-- FIX ICI
)

X = vectorizer.fit_transform(texts)
print("📌 Vectorisation terminée :", X.shape)

# ---------------------------------------------------------
# 3. Modèle Logistic Regression
# ---------------------------------------------------------

model = LogisticRegression(max_iter=500)
model.fit(X, labels)

print("📌 Modèle entraîné avec succès")

# ---------------------------------------------------------
# 4. Sauvegarde
# ---------------------------------------------------------

joblib.dump(vectorizer, "../models/vectorizer.pkl")
joblib.dump(model, "../models/email_classifier.pkl")

print("🎉 Modèle sauvegardé dans app/models/")
