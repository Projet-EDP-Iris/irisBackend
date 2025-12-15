# GitHub Actions Workflows

This directory contains automated workflows for the Iris Backend project.

## Workflows

### 🧪 Test ([test.yml](test.yml))
**Triggers:** Pull requests, pushes to main
- Runs the full test suite
- Tests against Python 3.12
- Uploads test results as artifacts
- **Status:** Required for PR merges

### 🎨 Lint ([lint.yml](lint.yml))
**Triggers:** Pull requests, pushes to main
- Runs Ruff linter for code quality
- Checks code formatting with Ruff
- Runs MyPy type checker
- **Status:** Recommended to pass before merging

### 🔒 Security ([security.yml](security.yml))
**Triggers:** Pull requests, pushes to main, weekly schedule
- Runs Bandit security scanner
- Checks for known vulnerabilities with pip-audit
- Uploads security reports as artifacts
- **Schedule:** Every Monday at 9am UTC

### 📊 Coverage ([coverage.yml](coverage.yml))
**Triggers:** Pull requests, pushes to main
- Runs tests with code coverage analysis
- Uploads coverage reports to Codecov
- Generates HTML coverage reports
- Enforces minimum 60% coverage threshold

### 📦 Dependency Update ([dependency-update.yml](dependency-update.yml))
**Triggers:** Weekly schedule, manual trigger
- Checks for outdated dependencies
- Generates dependency update reports
- **Schedule:** Every Monday at 10am UTC

### 🐳 Docker ([docker.yml](docker.yml))
**Triggers:** Pull requests, pushes to main, version tags
- Builds Docker images
- Tests Docker image functionality
- Pushes to Docker Hub on main branch
- **Note:** Requires DOCKER_USERNAME and DOCKER_PASSWORD secrets

## Required Secrets

For full functionality, configure these secrets in your repository settings:

- `DOCKER_USERNAME`: Docker Hub username (for docker.yml)
- `DOCKER_PASSWORD`: Docker Hub password or access token (for docker.yml)

## Status Badges

Add these to your main README.md:

```markdown
![Tests](https://github.com/YOUR_USERNAME/irisBackend/workflows/Run%20Tests/badge.svg)
![Lint](https://github.com/YOUR_USERNAME/irisBackend/workflows/Lint/badge.svg)
![Security](https://github.com/YOUR_USERNAME/irisBackend/workflows/Security%20Scan/badge.svg)
![Coverage](https://github.com/YOUR_USERNAME/irisBackend/workflows/Code%20Coverage/badge.svg)
```

## Local Testing

Before pushing, you can run these checks locally:

```bash
# Run tests
poetry run pytest -v

# Run linter
poetry run ruff check .

# Check formatting
poetry run ruff format --check .

# Run type checker
poetry run mypy app/ --ignore-missing-imports

# Run tests with coverage
poetry run pytest --cov=app --cov-report=html
```

## Troubleshooting

### Tests failing in CI but passing locally
- Ensure you've committed all changes
- Check that your local database schema matches the model definitions
- Delete local `.test.db` and `test.db` files and re-run tests

### Docker workflow failing
- Verify DOCKER_USERNAME and DOCKER_PASSWORD secrets are set
- Check that your Dockerfile is in the repository root
- Ensure the Docker image builds locally first

### Coverage threshold failing
- Run `poetry run pytest --cov=app --cov-report=term` locally
- Add tests for uncovered code
- Adjust the threshold in coverage.yml if needed (currently 60%)
