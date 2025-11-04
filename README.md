# Iris Backend API

This repo contains the backend API for the Iris application, built using **FastAPI** and **Python 3.12** and using **SQLAlchemy for Postgres** (Supabase) and **Pydantic** for validation.

The backend manages user data, events, scheduling, and integrates a custom **NLP/NER** (Named Entity Recognition) pipeline for processing email content.

Backend API for the Iris application built with FastAPI and Python 3.12, using SQLAlchemy for Postgres (Supabase) and Pydantic for validation.
It includes automatic interactive API documentation at /docs (Swagger UI) and /redoc (ReDoc) generated from the app’s OpenAPI schema.

## 🚀 Getting Started

## Features
- FastAPI app with a users endpoint and input validation via Pydantic schemas.
- SQLAlchemy ORM models backed by a Supabase Postgres database via a standard connection URL.
- Argon2 password hashing via passlib/argon2-cffi following OWASP guidance for password storage.
- Auto-generated docs available at /docs and /redoc for quick testing and team onboarding.

### Prerequisites/Requirements

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


3. Configure environment (.env in repo root)  
    ```bash
    DATABASE_URL=postgresql://<user>:<pass>@db.<ref>.supabase.co:5432/postgres
    SECRET_KEY=<random-32+chars>
    ```

4. Run the dev server  
poetry run uvicorn app.main:app --reload
    ```bash
    Open http://127.0.0.1:8000/docs for Swagger UI or http://127.0.0.1:8000/redoc for ReDoc to explore and test the API.
    ```

## Tests
    ```bash
    poetry run pytest -v
    ```
This runs the test suite against your FastAPI app and verifies endpoint behavior. [web:6]

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

## Notes
- Docs are enabled by default in FastAPI; you can customize or move them with docs_url/redoc_url if needed.
- Consider adding OAuth2 + JWT later so clients can log in and call protected endpoints with a Bearer token.
- For production schema changes, consider Alembic migrations instead of create_all for better change tracking.