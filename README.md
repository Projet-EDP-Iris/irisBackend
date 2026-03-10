# Iris Backend API

Backend API for the Iris application, built with **FastAPI** and **Python 3.12**. Manages user authentication, data processing, and integrates a custom **NLP/NER** pipeline for email content analysis.

**🚀 Deployed on:** [Render](https://render.com)

---

## Prerequisites

- Python 3.12+
- Poetry (package manager)
- Docker Desktop

---

## Quick Start

### 1. Clone and Install

```bash
# Clone repository
git clone <repository-url>
cd irisBackend

# Install dependencies
poetry install
```

### 2. Set Up Database

```bash
# Start PostgreSQL in Docker
docker-compose up -d

# Verify it's running
docker-compose ps
# Should show iris_postgres as "Up"
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env
# Defaults work for local development
```

### 4. Run the Application

```bash
poetry run uvicorn app.main:app --reload
```

### 5. Test the API

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## Testing

**What is testing?** Tests automatically verify that your code works correctly. They catch bugs before deployment and ensure new changes don't break existing features.

**Why test?**
- Prevents bugs from reaching production
- Documents how the code should behave
- Enables confident refactoring
- Required for all pull requests to pass CI/CD checks

**Run tests:**

```bash
# Run all tests
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=app --cov-report=html

# Run specific test file
poetry run pytest tests/test_user_api.py -v
```

**Coverage report:** After running with `--cov-report=html`, open `htmlcov/index.html` in your browser to see which code is tested.

You can also run pipeline and email tests: `poetry run pytest tests/test_emails_api.py tests/test_gmail_service.py -v`

---

## Pipeline: Gmail to detection to prediction

The backend wires three steps: **Gmail** (fetch emails), **detection** (extract intent, times, participants, etc.), and **prediction** (suggest meeting slots). Contracts are aligned: detection returns `ExtractionResult`(s); prediction accepts `ExtractionResult` (or a list and uses the first).

### One-shot: fetch, detect, and predict in one call

**POST /api/v1/emails/fetch-detect-predict** (JWT required)

- Fetches recent Gmail emails for the authenticated user, runs detection on each, then runs prediction on the first extraction and returns a combined result. Returns 404 if Gmail is not connected for this user.
- **Query:** `max_results` (default 10).
- **Body (optional):** `{ "preferences": { "working_hours": {...}, "preferred_duration_minutes": 30, "timezone": "Europe/Paris" }, "calendar": { "busy_slots": [...], "free_slots": [...] } }` for the prediction step.
- **Response:** `{ "emails": [...], "extractions": [...], "suggested_slots": [...], "status": "READY_TO_SCHEDULE" }`

### Step-by-step (call A then B then C)

1. **GET /api/v1/emails?max_results=10** (JWT) — Returns list of emails (subject, body, message_id, sender, date). 404 if Gmail not connected.
2. **POST /api/v1/emails/fetch-and-detect** (JWT) — Fetches and runs detection; returns `{ "emails": [...], "extractions": [...] }`. Or use **POST /detect** with body `{ "emails": [ { "subject", "body", "message_id" }, ... ] }` if you already have the emails.
3. **POST /api/v1/predict/slots/from-detection** — Body: `{ "extraction": <ExtractionResult or list>, "preferences": {...}, "calendar": {...} }`. Returns `{ "suggested_slots": [...], "status": "READY_TO_SCHEDULE" }`.

Detection returns `ExtractionResult` (classification, proposed_times, duration_minutes, timezone, participants, etc.). Prediction accepts that same shape; no contract change needed.

For detection endpoints and schemas, see `app/api/routes/detection.py` and `app/schemas/detection.py`. Detection endpoints are JWT-protected: POST `/detect`, `/detect/thread`, `/validate`, `/feedback`; they consume `EmailInput` and return `ExtractionResult` (or validation/feedback results).

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
docker-compose down -v
docker-compose up -d

# Access PostgreSQL shell
docker-compose exec postgres psql -U iris_user -d iris_db
```

---

## Contributing Workflow

We use **develop** as the integration branch. Feature branches merge into **develop**; when develop is stable, open a PR from **develop** to **main**. CI runs on pull requests to **develop** and **main** (tests, coverage, lint).

### Creating a Pull Request

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and commit:**
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

3. **Push to GitHub:**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create Pull Request on GitHub:**
   - Go to the repository on GitHub
   - Click "Pull requests" → "New pull request"
   - **Target branch:** **develop** (for feature branches) or **main** (for the release PR from develop)
   - Select your branch, fill in the PR template, and click "Create pull request"

5. **Wait for CI/CD checks:**
   - Tests must pass
   - Code coverage must meet threshold (60%)
   - Linting must pass

6. **Keep your branch up-to-date with develop:**
   ```bash
   # Fetch latest changes from develop
   git checkout develop
   git pull origin develop

   # Switch back to your branch and merge
   git checkout feature/your-feature-name
   git merge develop

   # Resolve any conflicts if needed
   # Then push updated branch
   git push origin feature/your-feature-name
   ```

7. **Request code review** and wait for approval

8. **Merge** after approval (GitHub will check that your branch is up-to-date)

**Important:** Your feature branch **must be up-to-date with develop** before merging into develop. For the release PR (develop → main), develop must be up-to-date with main if you've changed the default branch. Update your branch using the steps in #6 when needed.

---

## Project Architecture

**Note:** This structure evolves as the project grows.

```
irisBackend/
├── app/
│   ├── api/
│   │   ├── endpoints/    # /api/v1 routes (prediction, emails)
│   │   │   ├── prediction.py
│   │   │   └── emails.py
│   │   └── routes/       # Route handlers (users, detection)
│   │       ├── users.py
│   │       └── detection.py
│   ├── core/             # Config, auth, security
│   │   ├── auth.py
│   │   ├── config.py
│   │   └── security.py
│   ├── db/               # Database connection and session
│   ├── models/           # SQLAlchemy models (user, feedback, etc.)
│   ├── schemas/          # Pydantic schemas (detection, prediction, email, user)
│   ├── services/         # Business logic
│   │   ├── detection.py
│   │   ├── prediction_service.py
│   │   └── gmail_service.py
│   ├── nlp/              # NLP (SpaCy, extractor, LLM fallback)
│   └── main.py           # FastAPI app entry point
├── tests/                # Automated tests
├── .github/workflows/    # CI/CD (tests, linting, coverage, security)
├── docker-compose.yml    # PostgreSQL
└── pyproject.toml        # Dependencies and project metadata
```

**Key Components:**
- **api/endpoints/** - `/api/v1` routes: prediction (slot suggestions from extraction), emails (Gmail fetch, fetch-and-detect, fetch-detect-predict)
- **api/routes/** - Users (auth, CRUD) and detection (extract intent/times from emails; JWT-protected)
- **services/** - Detection (NLP + optional LLM), prediction (slot scoring), Gmail (token by user_id, full body, message_id)
- **schemas/** - Request/response contracts (detection, prediction, email)
- **models/** - Database tables (users, detection feedback)
- **core/** - Security, config, authentication
- **tests/** - Automated verification

---

## Code Style Guidelines

- Follow PEP 8 style guidelines
- Use type hints for all functions
- Write docstrings for public functions
- Keep functions focused and single-purpose
- Write tests for all new features

---

## Common Issues

**Port 5432 already in use:**
```bash
# Stop local PostgreSQL
brew services stop postgresql  # macOS
sudo systemctl stop postgresql  # Linux

# Or change Docker port in docker-compose.yml to 5433:5432
```

**Connection refused to database:**
```bash
# Ensure Docker is running
docker-compose ps
docker-compose up -d
```

**ModuleNotFoundError:**
```bash
poetry install
```
