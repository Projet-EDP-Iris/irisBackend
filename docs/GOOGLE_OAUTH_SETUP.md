# Google OAuth Setup (Gmail + Calendar + Tasks)

This guide walks you through setting up Google OAuth so the backend can access Gmail, Google Calendar, and Google Tasks on behalf of your users.

---

## Prerequisites

- A Google account
- Access to [Google Cloud Console](https://console.cloud.google.com/)

---

## Step 1 — Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Give it a name (e.g. `iris-backend`) and click **Create**
4. Make sure the new project is selected in the dropdown

---

## Step 2 — Enable the Required APIs

In your project, go to **APIs & Services → Library** and enable all three:

- **Gmail API** — search "Gmail API" → Enable
- **Google Calendar API** — search "Google Calendar API" → Enable
- **Google Tasks API** — search "Tasks API" → Enable

---

## Step 3 — Configure the OAuth Consent Screen

1. Go to **APIs & Services → OAuth consent screen**
2. Select **External** (allows any Google account to sign in) → **Create**
3. Fill in:
   - **App name:** Iris
   - **User support email:** your email
   - **Developer contact:** your email
4. Click **Save and Continue**
5. On the **Scopes** step, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/tasks`
6. Click **Update → Save and Continue**
7. On the **Test users** step, add the email addresses that will use the app during development (required while the app is in "Testing" status)
8. Click **Save and Continue**

> **Publishing:** While the consent screen is in "Testing" mode, only the listed test users can authenticate. To allow anyone, click **Publish App** — this requires Google's verification for sensitive scopes.

---

## Step 4 — Create OAuth 2.0 Credentials

1. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Web application**
3. Under **Authorised redirect URIs**, add:
   - `http://localhost:8000/api/v1/auth/google/callback` (local development)
   - Your production URL equivalent (e.g. `https://your-api.onrender.com/api/v1/auth/google/callback`)
4. Click **Create**
5. Click **Download JSON** — this is your `credentials.json` file

---

## Step 5 — Place credentials.json

Move the downloaded file to the **root of the irisBackend project** (same level as `pyproject.toml`):

```
irisBackend/
├── credentials.json   ← here
├── app/
├── pyproject.toml
└── ...
```

`credentials.json` is in `.gitignore` — never commit it.

---

## Step 6 — Set Environment Variables

In your `.env` file:

```env
GOOGLE_CLIENT_ID=<your-client-id-from-step-4>
GOOGLE_CLIENT_SECRET=<your-client-secret-from-step-4>
GMAIL_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
FRONTEND_URL=http://localhost:5173
```

---

## Step 7 — Run the OAuth Flow

With the backend running, navigate a user through the flow:

1. Call `GET /api/v1/auth/google` — returns a Google authorization URL
2. Open the URL in a browser, sign in with the test Google account, and approve the requested scopes
3. Google redirects back to `GMAIL_REDIRECT_URI` — the backend stores the token at `tokens/gmail_user_<id>.json`

The user is now connected. Gmail fetch, Calendar, and Tasks will all work using this token.

---

## Token Storage

OAuth tokens are saved locally to `tokens/gmail_user_<id>.json`. This works in local development, but the files are lost on ephemeral deployments. See [DEPLOYMENT.md](DEPLOYMENT.md) for the production workaround.

---

## Troubleshooting

**"Access blocked: app has not completed Google verification"**
Add the signing-in email as a test user in the OAuth consent screen (Step 3, test users).

**Calendar or Tasks returning 403 after adding new scopes**
The stored token was issued before the new scopes were requested. Delete the token file and re-run the OAuth flow:
```bash
rm tokens/gmail_user_<id>.json
```

**"redirect_uri_mismatch"**
The redirect URI in your `.env` must exactly match one of the URIs registered in Step 4 (including `http` vs `https` and trailing slashes).
