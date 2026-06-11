# Iris Backend API

Backend API for the Iris application, built with **FastAPI** and **Python 3.12**. Manages user authentication, Gmail integration, NLP email analysis, meeting slot prediction, multi-provider calendar sync, and AI-generated reply drafts.

**Deployed on:** [Render](https://render.com) · **Frontend:** [irisFrontendApp](https://github.com/Projet-EDP-Iris/irisFrontendApp) — React + Electron desktop app

---

## Download & Presentation

| | |
|---|---|
| **Download the app** | [one-page-site-ten.vercel.app](https://one-page-site-ten.vercel.app/) |
| **Presentation** | [![View on Canva](https://img.shields.io/badge/Canva-Presentation-blue?logo=canva)](https://canva.link/irisinc) |

---

## Prerequisites

- Python 3.12+
- Poetry (package manager)
- Docker Desktop

---

## Environment Variables

Create a `.env` file at the project root:

```env
# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://iris_user:iris_password@localhost:5432/iris_db

# ── JWT authentication ────────────────────────────────────────────────────────
SECRET_KEY=<your-secret-key>

# ── Encryption (required for Apple Calendar) ──────────────────────────────────
# Generate once: poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Never change this after first use — it will invalidate stored Apple passwords.
SECRET_ENCRYPTION_KEY=<generated-fernet-key>

# ── OpenAI (optional — RDV metadata extraction + auto-reply drafting) ────────
OPENAI_API_KEY=<your-openai-key>

# ── textcat classifier (optional — local email classification, zero API cost) ──
# Train once: poetry run python -m app.ML.export_training_data && poetry run python -m app.ML.train_textcat
# TEXTCAT_MODEL_PATH=app/ML/models/iris_textcat   # default, no need to set unless custom
# TEXTCAT_CONFIDENCE_THRESHOLD=0.65               # default

# ── Google OAuth (Gmail + Calendar + Tasks) ───────────────────────────────────
# Configured via credentials.json from Google Cloud Console — no .env vars needed
# for the core flow. Optional overrides:
GOOGLE_CLIENT_ID=<from-google-cloud-console>
GOOGLE_CLIENT_SECRET=<from-google-cloud-console>
GMAIL_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:5173

# ── Microsoft / Outlook (Calendar + Tasks) ────────────────────────────────────
# Register an app at https://portal.azure.com → App registrations → New registration
# Required API permissions: Calendars.ReadWrite, Tasks.ReadWrite, offline_access, User.Read
MICROSOFT_CLIENT_ID=<from-azure-portal>
MICROSOFT_CLIENT_SECRET=<from-azure-portal>
MICROSOFT_TENANT_ID=common
# "common" = any Microsoft account; replace with your org tenant ID for org-only access
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/auth/microsoft/callback
```

---

## Quick Start

Follow these steps **in order** every time you want to run the backend locally.

### Step 1 — Install dependencies (first time only)

```bash
poetry install
```

Only needed once when you first clone the repo, or after pulling changes that added new packages.

### Step 2 — Start Docker Desktop

Open the **Docker Desktop** app on your Mac and wait until it says **"Engine running"** in the bottom left.

### Step 3 — Start the database

```bash
docker-compose up -d
```

Wait 5–10 seconds for PostgreSQL to finish initialising. To confirm it's ready:

```bash
docker-compose ps
# You should see iris_postgres with status "Up (healthy)"
```

### Step 4 — Start the backend

```bash
poetry run uvicorn app.main:app --reload --port 8000
```

The API is now live at **http://localhost:8000**
Interactive docs at **http://localhost:8000/docs**

For Gmail OAuth locally, make sure your Google Cloud OAuth redirect URI exactly matches:

```text
http://localhost:8000/api/v1/auth/google/callback
```

The frontend currently uses hash routing, so the backend must redirect back to the frontend origin and let the SPA land on `#/emails`.

### Stopping everything

```bash
# Stop the backend: CTRL+C in the terminal
docker-compose down
```

### Test the API

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## Testing

Tests automatically verify that the code works correctly. They catch bugs before deployment and ensure changes don't break existing features.

```bash
# Run all tests
poetry run pytest -v

# Run with coverage (shows which lines have no test)
poetry run pytest --cov=app --cov-report=term-missing

# HTML coverage report — open htmlcov/index.html in a browser
poetry run pytest --cov=app --cov-report=html

# Run a specific file
poetry run pytest tests/test_user_api.py -v

# Calendar feature tests
poetry run pytest tests/test_encryption.py tests/test_calendar_services_unit.py tests/test_calendar_api.py -v
```

**Test files:**

| File | What it tests |
|---|---|
| `test_user_api.py` | User registration, login, CRUD, permissions |
| `test_user_model.py` | User model validation |
| `test_detection_api.py` | NLP extraction endpoints |
| `test_detection_extractor_unit.py` | Regex + dateparser extraction logic |
| `test_detection_llm_fallback.py` | OpenAI fallback behaviour |
| `test_emails_api.py` | Gmail fetch pipeline endpoints |
| `test_gmail_service.py` | Gmail OAuth token management |
| `test_google_oauth_service.py` | Google OAuth service logic |
| `test_auth_api.py` | Email verification and password reset flows |
| `test_auth_google.py` | Google OAuth callback handling |
| `test_apple_calendar.py` | Apple CalDAV connection and event creation |
| `test_outlook_emails.py` | Outlook email parsing |
| `test_prediction.py` / `test_prediction_api.py` / `test_prediction_service.py` | Slot prediction logic and endpoints |
| `test_suggestion_api.py` | `/suggest/{email_id}` and `/suggest-inline` endpoints |
| `test_encryption.py` | Fernet encrypt/decrypt round-trip and error handling |
| `test_calendar_services_unit.py` | Google Calendar + Apple CalDAV services (all external calls mocked) |
| `test_calendar_api.py` | `/calendar/confirm` and `/me/calendar-setup` integration tests |
| `test_main.py` | Root and health check endpoints |

---

## Full Pipeline

### Architecture

```
Gmail → Detection (NLP) → Prediction (slots) → Suggestion (reply draft)
                                                      ↓
                              Calendar Confirm → Google Calendar
                                              → Apple Calendar
                                              → Outlook Calendar
                                              → Google Tasks
                                              → Outlook Tasks (Microsoft To Do)
```

### One-shot endpoint

```
POST /emails/fetch-detect-predict
Authorization: Bearer <token>
```

Fetches Gmail emails, runs NLP extraction on each, runs slot prediction on the first result. Returns emails, extractions, and suggested slots in one call.

### Step-by-step

1. `GET /emails?max_results=10` — fetch raw Gmail emails
2. `POST /emails/fetch-and-detect` — fetch + NLP extraction
3. `POST /predictions/predict/slots/{email_id}` — predict meeting slots
4. `POST /suggestions/suggest/{email_id}` — generate reply draft
5. `POST /api/v1/calendar/confirm/{email_id}` — one-click: create events in all calendars

---

## One-Click Calendar Integration

### Connect a calendar (one-time per provider)

**Google Calendar:**
```
PATCH /api/v1/user/users/me/calendar-setup
{ "calendar_provider": "google" }
```
Reuses the existing Gmail OAuth token — no extra credentials needed.

**Apple Calendar:**
```
PATCH /api/v1/user/users/me/calendar-setup
{
  "calendar_provider": "apple",
  "apple_caldav_user": "yourname@icloud.com",
  "apple_caldav_password": "xxxx-xxxx-xxxx-xxxx"
}
```
The App Password is generated at [appleid.apple.com](https://appleid.apple.com) → Security → App Passwords. It is Fernet-encrypted before storage — the plain text is never persisted.

**Outlook / Microsoft 365:**
```
# Step 1 — initiate OAuth (returns a URL to open in the browser)
GET /api/v1/auth/microsoft
Authorization: Bearer <token>

# Step 2 — Microsoft redirects back automatically after login
GET /api/v1/auth/microsoft/callback?code=...&state=...

# Step 3 — register as a provider
PATCH /api/v1/user/users/me/calendar-setup
{ "calendar_provider": "outlook" }
```

**Connect multiple providers** — call `/me/calendar-setup` once per provider. Each call appends to the list. To disconnect: `DELETE /api/v1/user/users/me/calendar-disconnect?provider=apple`

### Confirm a meeting in one click

```
POST /api/v1/calendar/confirm/{email_id}
Authorization: Bearer <token>
{ "slot_index": 0 }
```

This single call:
1. Creates the event in **every connected calendar** (Google, Apple, Outlook)
2. Creates a **task reminder** in Google Tasks and/or Microsoft To Do
3. **Prepares a reply email draft** (stored in the Email record)
4. Marks the email as `confirmed` in the database

```json
{
  "status": "confirmed",
  "slot": { "start_time": "2024-10-18T10:00:00", "end_time": "2024-10-18T11:00:00" },
  "providers": [
    { "provider": "google", "event_id": "abc123", "task_id": "tsk_xyz" },
    { "provider": "apple",  "event_id": "uuid-...", "task_id": null },
    { "provider": "outlook","event_id": "AAMk...", "task_id": "task_id" }
  ],
  "calendar_event_ids": { "google": "abc123", "apple": "uuid-...", "outlook": "AAMk..." },
  "prepared_reply": "Hello,\n\nThank you for your message..."
}
```

Partial failures (one provider down) are logged and reported per-provider without blocking the others.

> **Note on re-authentication:** The `calendar` and `tasks` Google scopes were added after the initial Gmail integration. Users who connected Gmail earlier need to re-authenticate once (delete `tokens/gmail_user_<id>.json` and run the OAuth flow again).

> **Note on token storage:** Gmail OAuth credentials are currently written to `tokens/gmail_user_<id>.json` on local disk. This works in local development, but ephemeral hosting can lose those files on restart or redeploy. If Gmail keeps disconnecting after deploys, move OAuth credentials to persistent storage. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for details.

---

## Docker Commands

```bash
# Start database
docker-compose up -d

# Stop database
docker-compose down

# View logs
docker-compose logs -f postgres

# Reset database (deletes all data)
docker-compose down -v && docker-compose up -d

# Access PostgreSQL shell
docker-compose exec postgres psql -U iris_user -d iris_db
```

---

## Contributing Workflow

We use **develop** as the integration branch. Feature branches merge into **develop**; when develop is stable, open a PR from **develop** to **main**. CI runs on pull requests to **develop** and **main** (tests, coverage, lint).

1. `git checkout -b feature/your-feature-name`
2. Make changes, commit
3. `git push origin feature/your-feature-name`
4. Open PR targeting **develop** on GitHub
5. CI must pass (tests, coverage ≥ 60%, lint)
6. Keep branch up-to-date: `git merge develop` before merging

---

## Project Architecture

```
irisBackend/
├── app/
│   ├── api/
│   │   ├── endpoints/                  # /api/v1 routes
│   │   │   ├── calendar.py             # POST /calendar/confirm — multi-provider sync
│   │   │   ├── emails.py               # Gmail fetch + full pipeline endpoint
│   │   │   ├── prediction.py           # POST /predict/slots — slot suggestions
│   │   │   └── suggestion.py           # POST /suggest — AI reply draft
│   │   └── routes/
│   │       ├── auth.py                 # Email verification, password reset
│   │       ├── auth_apple.py           # Apple iCloud CalDAV setup
│   │       ├── auth_google.py          # Google OAuth callback
│   │       ├── auth_microsoft.py       # Microsoft OAuth flow
│   │       ├── detection.py            # POST /detect, /validate, /feedback
│   │       └── users.py                # Auth, CRUD, calendar setup/disconnect
│   ├── core/
│   │   ├── auth.py                     # JWT bearer dependency (get_current_active_user)
│   │   ├── config.py                   # All settings (DB, JWT, Google, Microsoft)
│   │   ├── encryption.py               # Fernet encrypt/decrypt for Apple passwords
│   │   ├── rate_limiter.py             # Sliding-window rate limiter
│   │   └── security.py                 # JWT creation, Argon2 password hashing
│   ├── db/
│   │   └── database.py                 # SQLAlchemy engine, session, init_db()
│   ├── models/
│   │   ├── base.py                     # Base + TimestampMixin
│   │   ├── auth_token.py               # Email verification and password-reset tokens
│   │   ├── user.py                     # User table (auth + calendar_providers JSON)
│   │   ├── email.py                    # Email pipeline state machine
│   │   └── feedback.py                 # Detection correction feedback
│   ├── schemas/
│   │   ├── auth.py                     # ChangePasswordRequest, MessageResponse
│   │   ├── detection.py                # ExtractionResult, TimeWindow, Participant
│   │   ├── email.py                    # EmailItem, FetchDetectPredictResponse
│   │   ├── prediction.py               # RecommendedSlot, PredictionResponse
│   │   ├── suggestion.py               # SuggestionResponse
│   │   └── user.py                     # UserCreate, UserResponse, UserUpdate
│   ├── services/
│   │   ├── detection.py                # NLP detection + LLM fallback orchestration
│   │   ├── prediction_service.py       # Slot scoring, working hours, timezone
│   │   ├── gmail_service.py            # Gmail OAuth, token management, email fetch
│   │   ├── google_calendar_service.py  # Google Calendar API (reuses Gmail token)
│   │   ├── google_tasks_service.py     # Google Tasks API (reuses Gmail token)
│   │   ├── apple_calendar_service.py   # Apple iCloud CalDAV + App Password
│   │   ├── microsoft_oauth_service.py  # MS OAuth2 token storage/refresh via httpx
│   │   ├── outlook_calendar_service.py # Microsoft Graph API — calendar events
│   │   ├── outlook_tasks_service.py    # Microsoft Graph API — To Do tasks
│   │   ├── outlook_email_service.py    # Outlook email fetch
│   │   ├── openai_service.py           # OpenAI GPT reply generation (mock → real)
│   │   ├── suggestion_service.py       # Reply draft formatter
│   │   ├── auth_token_service.py       # Token creation/consumption for auth flows
│   │   └── email_service.py            # SMTP email sending
│   ├── nlp/
│   │   ├── extractor.py                # Regex + spaCy + textcat NLP engine
│   │   ├── preprocessor.py             # Zero-shot pre-filter (noreply / unsubscribe)
│   │   ├── textcat_classifier.py       # Singleton inference wrapper for trained textcat
│   │   └── llm_fallback_openai.py      # GPT fallback when NLP confidence < 0.6
│   ├── ML/
│   │   ├── export_training_data.py     # DB → spaCy .spacy training corpus
│   │   ├── train_textcat.py            # Train textcat + per-category F-score report
│   │   ├── retrain_from_feedback.py    # Analyse user corrections → pattern suggestions
│   │   └── configs/textcat.cfg         # TextCatEnsemble.v2 training config
│   └── main.py                         # FastAPI app, router registration, CORS
├── tests/                              # pytest test suite
├── docs/                               # Integration setup guides
│   ├── GOOGLE_OAUTH_SETUP.md
│   ├── APPLE_CALENDAR_SETUP.md
│   ├── MICROSOFT_OAUTH_SETUP.md
│   └── DEPLOYMENT.md
├── tokens/                             # Per-user OAuth token files (gitignored)
│   ├── gmail_user_<id>.json
│   └── outlook_user_<id>.json
├── .github/workflows/                  # CI/CD pipelines
├── docker-compose.yml                  # PostgreSQL + API containers
└── pyproject.toml                      # Poetry dependencies + tool config
```

---

## Code Style

- PEP 8, type hints on all functions
- No comments unless the WHY is non-obvious
- Tests required for all new features
- `poetry run ruff check app/` — lint
- `poetry run mypy app/` — type check

---

## Integration Setup Guides

Third-party integrations have dedicated step-by-step setup docs in the [`docs/`](docs/) folder:

- [Google OAuth (Gmail + Calendar + Tasks)](docs/GOOGLE_OAUTH_SETUP.md)
- [Apple Calendar (iCloud CalDAV + App Password)](docs/APPLE_CALENDAR_SETUP.md)
- [Microsoft / Outlook (Azure App Registration)](docs/MICROSOFT_OAUTH_SETUP.md)
- [Production Deployment on Render](docs/DEPLOYMENT.md)
- [Email Triage Algorithm](docs/TRIAGE_ALGORITHM.md)
- [AI Features: Summarize, Reply, Auto-draft](docs/AI_FEATURES.md)

---

## Common Issues

**Port 5432 already in use:**
```bash
brew services stop postgresql   # stop local Postgres on macOS
# or change the port in docker-compose.yml to 5433:5432
```

**Connection refused to database:**
```bash
docker-compose ps        # check it's running
docker-compose up -d     # start if not
```

**ModuleNotFoundError:**
```bash
poetry install
```

**Google Calendar / Tasks not working after recent update:**
New OAuth scopes (`calendar`, `tasks`) were added. Delete the user's token file and re-authenticate:
```bash
rm tokens/gmail_user_<id>.json
# Then re-run the Gmail OAuth flow
```

**Outlook not connecting:**
Ensure `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET` are set in `.env`, and that the redirect URI in Azure matches `MICROSOFT_REDIRECT_URI`.
