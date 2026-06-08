# Production Deployment on Render

Iris Backend is deployed on [Render](https://render.com). This document covers everything you need to configure for a production deployment.

---

## Prerequisites

- A Render account
- The repository pushed to GitHub (Render deploys from GitHub)
- All third-party credentials set up (Google OAuth, Microsoft Azure) — see the other docs in this folder

---

## Step 1 — Create a PostgreSQL Database on Render

1. In the Render dashboard, click **New → PostgreSQL**
2. Give it a name (e.g. `iris-db`) and choose a region
3. Click **Create Database**
4. Copy the **Internal Database URL** — you'll use this as `DATABASE_URL`

---

## Step 2 — Create the Web Service

1. Click **New → Web Service** and connect your GitHub repository
2. Configure:
   - **Runtime:** Python 3
   - **Build command:** `pip install poetry && poetry install --no-root`
   - **Start command:** `poetry run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/health`

---

## Step 3 — Set Environment Variables

In the Render dashboard under **Environment**, add all variables from `.env.example`:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Use the Internal Database URL from Step 1 |
| `SECRET_KEY` | Generate with `openssl rand -hex 32` |
| `SECRET_ENCRYPTION_KEY` | Generate once with the Fernet command in the README. **Never change after first deploy.** |
| `OPENAI_API_KEY` | Optional — enables the real LLM fallback |
| `GOOGLE_CLIENT_ID` | From Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | From Google Cloud Console |
| `GMAIL_REDIRECT_URI` | `https://your-api.onrender.com/api/v1/auth/google/callback` |
| `FRONTEND_URL` | Your frontend's production URL |
| `MICROSOFT_CLIENT_ID` | From Azure App Registration |
| `MICROSOFT_CLIENT_SECRET` | From Azure App Registration |
| `MICROSOFT_TENANT_ID` | `common` (or your org tenant ID) |
| `MICROSOFT_REDIRECT_URI` | `https://your-api.onrender.com/api/v1/auth/microsoft/callback` |
| `ENVIRONMENT` | `production` |

---

## Step 4 — Add credentials.json as a Secret File

`credentials.json` (Google OAuth client secrets) is not committed to git. Add it as a Render secret file:

1. In the Web Service settings, go to **Secret Files**
2. Click **Add Secret File**
3. Filename: `credentials.json`
4. Contents: paste the full contents of your local `credentials.json`

Render mounts this file at the specified path at startup.

---

## Step 5 — Update CORS Origins

In `app/main.py`, add your Render service URL to `ALLOWED_ORIGINS`:

```python
ALLOWED_ORIGINS = [
    ...
    "https://your-api.onrender.com",
    "https://your-frontend.vercel.app",
]
```

Commit and push — Render redeploys automatically.

---

## Persistent Token Storage (Important)

OAuth tokens for Gmail and Outlook are currently stored in `tokens/gmail_user_<id>.json` and `tokens/outlook_user_<id>.json` on the local filesystem. Render's filesystem is **ephemeral** — these files are lost on every redeploy or restart.

**What this means:** Users will need to re-authenticate with Gmail and Outlook after every deployment.

**Mitigation options:**

1. **Render Disk (recommended):** Attach a persistent disk to the web service and update the token path in `app/services/gmail_service.py` and `app/services/microsoft_oauth_service.py` to write to the mounted disk path.

2. **Store tokens in the database:** Encrypt the token JSON and store it in a `User` column. This is the most robust long-term solution.

Until one of these is implemented, tokens will be lost on redeploy and users must re-run the OAuth flow.

---

## Startup Behaviour

On startup, the API:
1. Runs `init_db()` — creates any missing database tables (safe to run repeatedly)
2. Pre-warms the spaCy NLP model — this adds ~30 seconds to the cold start

Render's health check (configured in Step 2) polls `GET /health`. Set the health check grace period to at least 60 seconds to account for the spaCy warm-up.

---

## Scaling

The current architecture is designed for a single-instance deployment. The main constraints are:
- **spaCy model:** loaded into memory once per instance — each additional instance loads its own copy
- **Token files:** if using filesystem storage (not recommended for production), multiple instances cannot share token files

For most current usage, a single Render instance is sufficient.
