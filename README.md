# Iris Backend API

This repo contains the backend API for the Iris application, built using **FastAPI** and **Python 3.12**.

The backend manages user data, events, scheduling, and integrates a custom **NLP/NER** (Named Entity Recognition) pipeline for processing email content.

## 🚀 Getting Started

### Prerequisites

* Python 3.12+
* Poetry (for dependency management)

### Setup

1.  **Clone the repository:**
    ```bash
    git clone [YOUR_REPO_URL]
    cd irisBackend
    ```

2.  **Install dependencies using Poetry:**
    ```bash
    poetry install
    ```

3.  **Run the server in development mode:**
    ```bash
    poetry run uvicorn app.main:app --reload
    ```
    The API will be accessible at: `http://127.0.0.1:8000`

### Running Tests

To run the unit tests:
```bash
poetry run pytest
```

## 📂 Project Structure

```
irisBackend/
├── app/
│   ├── api/          # API routers/controllers
│   ├── core/         # Settings, logging, and application configuration
│   ├── db/           # Database connection and session logic
│   ├── models/       # SQLAlchemy/Pydantic models
│   ├── nlp/          # NLP processing logic (SpaCy/NLTK)
│   ├── schemas/      # Pydantic data schemas
│   ├── services/     # Business logic layer
│   └── main.py       # FastAPI application entry point
├── tests/            # Unit and integration tests
├── .gitignore
├── pyproject.toml    # Poetry dependency file
└── README.md
```
