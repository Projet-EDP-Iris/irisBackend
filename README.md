# Iris Backend API

This repo contains the backend API for the Iris application, built using **FastAPI** and **Python 3.12** and using **SQLAlchemy for PostgreSQL** and **Pydantic** for validation.

The backend manages user data, events, scheduling, and integrates a custom **NLP/NER** (Named Entity Recognition) pipeline for processing email content.

## Prerequisites

- Python 3.12+
- Poetry (package manager)
- Docker Desktop

## Quick Start

1. **Clone repository**
   ```bash
   git clone <repository-url>
   cd irisBackend
   ```

2. **Install dependencies**
   ```bash
   poetry install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env if needed (defaults work for local development)
   ```

4. **Start Docker services**
   ```bash
   docker-compose up -d
   ```

5. **Verify database is running**
   ```bash
   docker-compose ps
   # Should show iris_postgres as "Up"
   ```

6. **Run application**
   ```bash
   poetry run uvicorn app.main:app --reload
   ```

7. **Access API documentation**
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Docker Commands

**Start services:**
```bash
docker-compose up -d
```

**Stop services:**
```bash
docker-compose down
```

**View logs:**
```bash
docker-compose logs -f postgres
```

**Reset database (delete all data):**
```bash
docker-compose down -v
docker-compose up -d
```

**Access PostgreSQL shell:**
```bash
docker-compose exec postgres psql -U iris_user -d iris_db
```

## Testing

```bash
# Run all tests
poetry run pytest -v

# Run specific test file
poetry run pytest tests/test_user_api.py -v
```

## Troubleshooting

**Port 5432 already in use:**
- Another PostgreSQL instance is running
- Stop it: `brew services stop postgresql` (macOS)
- Or change Docker port in `docker-compose.yml`: `"5433:5432"`

**"Connection refused" error:**
- Ensure Docker is running: `docker-compose ps`
- Check logs: `docker-compose logs postgres`
- Restart services: `docker-compose restart`

**"Authentication failed" error:**
- Verify `.env` credentials match `docker-compose.yml`
- DATABASE_URL should use `iris_user:iris_password`

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

## Contributing to Iris

### Daily Development Workflow

**Starting work:**
```bash
# Start Docker services
docker-compose up -d

# Verify services are healthy
docker-compose ps

# Run application
poetry run uvicorn app.main:app --reload
```

**Ending work:**
```bash
# Stop Docker services (optional - saves resources)
docker-compose down
```

### Database Operations

**Reset database (clean slate):**
```bash
docker-compose down -v
docker-compose up -d
```

**Inspect database:**
```bash
# Access PostgreSQL shell
docker-compose exec postgres psql -U iris_user -d iris_db

# List tables
\dt

# Query users
SELECT * FROM users;

# Exit
\q
```

### Running Tests

```bash
# Run all tests
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=app tests/
```

### Git Workflow

1. Create feature branch: `git checkout -b feature/your-feature-name`
2. Make changes and commit: `git commit -m "Description"`
3. Push to remote: `git push origin feature/your-feature-name`
4. Create Pull Request on GitHub
5. Wait for tests to pass (GitHub Actions)
6. Request code review
7. Merge after approval

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for function parameters and return values
- Write docstrings for all functions and classes
- Keep functions focused and single-purpose
- Use meaningful variable names

### Testing Guidelines

- Write tests for all new features
- Maintain test coverage above 80%
- Use descriptive test names that explain what is being tested
- Include both positive and negative test cases

### Common Issues

**"ModuleNotFoundError":**
- Run `poetry install` to install dependencies

**"Connection refused" to database:**
- Run `docker-compose up -d` to start PostgreSQL
- Check logs: `docker-compose logs postgres`

**"Port 5432 already in use":**
- Another PostgreSQL is running on your system
- Stop it or change port in `docker-compose.yml` to `5433:5432`
- Update `.env` to use port 5433

**Docker containers won't start:**
- Ensure Docker Desktop is running
- Restart Docker Desktop
- Run `docker-compose down` then `docker-compose up -d`