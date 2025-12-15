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
   - Select your branch
   - Fill in the PR template
   - Click "Create pull request"

5. **Wait for CI/CD checks:**
   - Tests must pass ✅
   - Code coverage must meet threshold ✅
   - Linting must pass ✅

6. **Keep your branch up-to-date with main:**
   ```bash
   # Fetch latest changes from main
   git checkout main
   git pull origin main

   # Switch back to your branch and merge
   git checkout feature/your-feature-name
   git merge main

   # Resolve any conflicts if needed
   # Then push updated branch
   git push origin feature/your-feature-name
   ```

7. **Request code review** and wait for approval

8. **Merge** after approval (GitHub will check that your branch is up-to-date)

**Important:** Your branch **must be up-to-date with main** before merging. If main has new commits after you created your PR, update your branch using the steps in #6.

---

## Project Architecture

**Note:** This structure evolves as the project grows.

```
irisBackend/
├── app/
│   ├── api/              # API endpoints and routes
│   │   └── routes/       # Route handlers (users, events, etc.)
│   ├── core/             # Core application config
│   │   ├── auth.py       # Authentication logic
│   │   ├── config.py     # Settings and environment variables
│   │   └── security.py   # Password hashing, JWT tokens
│   ├── db/               # Database connection and session
│   ├── models/           # SQLAlchemy database models
│   │   ├── base.py       # Base model and mixins
│   │   └── user.py       # User model
│   ├── schemas/          # Pydantic request/response schemas
│   ├── nlp/              # NLP processing (SpaCy, NLTK)
│   └── main.py           # FastAPI app entry point
├── tests/                # Automated tests
├── .github/
│   └── workflows/        # CI/CD automation (tests, linting, security)
├── docker-compose.yml    # PostgreSQL database configuration
└── pyproject.toml        # Dependencies and project metadata
```

**Key Components:**
- **models/** - Database tables (what data we store)
- **schemas/** - API request/response formats (how data moves in/out)
- **api/routes/** - Endpoint logic (what happens when you call `/users`)
- **core/** - Security, config, authentication
- **tests/** - Automated verification that everything works

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
