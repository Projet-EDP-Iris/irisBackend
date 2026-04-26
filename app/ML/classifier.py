import joblib
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")

vectorizer = joblib.load(os.path.join(MODEL_DIR, "vectorizer.pkl"))
model = joblib.load(os.path.join(MODEL_DIR, "email_classifier.pkl"))

def classify_email(subject: str, body: str) -> str:
    text = (subject + " " + body).lower()
    X = vectorizer.transform([text])
    return model.predict(X)[0]
