# Microsoft / Outlook OAuth Setup (Azure App Registration)

Iris connects to Outlook Calendar and Microsoft To Do via the Microsoft Graph API, using OAuth 2.0. You need to register an application in Azure Active Directory to get the credentials.

---

## Prerequisites

- A Microsoft account (personal Outlook or work/school account)
- Access to [Azure Portal](https://portal.azure.com/)

---

## Step 1 — Register an Application in Azure

1. Go to [portal.azure.com](https://portal.azure.com/) and sign in
2. Search for **Azure Active Directory** in the top search bar → click it
3. In the left sidebar, click **App registrations → New registration**
4. Fill in:
   - **Name:** Iris Backend
   - **Supported account types:** select **Accounts in any organizational directory and personal Microsoft accounts** (this covers both Outlook.com and work accounts)
   - **Redirect URI:** select `Web` and enter `http://localhost:8000/api/v1/auth/microsoft/callback`
5. Click **Register**

You'll land on the app's overview page. Copy the **Application (client) ID** and the **Directory (tenant) ID** — you'll need these for `.env`.

---

## Step 2 — Add a Client Secret

1. In the left sidebar of your app, click **Certificates & secrets → New client secret**
2. Give it a description (e.g. `iris-backend`) and choose an expiry
3. Click **Add**
4. **Copy the Value immediately** — you cannot see it again after leaving this page

---

## Step 3 — Add API Permissions

1. In the left sidebar, click **API permissions → Add a permission → Microsoft Graph → Delegated permissions**
2. Search for and select:
   - `Calendars.ReadWrite`
   - `Tasks.ReadWrite`
   - `offline_access` (required for refresh tokens)
   - `User.Read`
3. Click **Add permissions**
4. If you're using a work/school account: click **Grant admin consent for [your org]** — this is required for work tenants. Personal accounts don't need this step.

---

## Step 4 — Add the Production Redirect URI

If deploying to production, add your production callback URL to the app registration:

1. In the left sidebar, click **Authentication**
2. Under **Web → Redirect URIs**, click **Add URI** and enter:
   `https://your-api.onrender.com/api/v1/auth/microsoft/callback`
3. Click **Save**

---

## Step 5 — Set Environment Variables

In your `.env` file:

```env
MICROSOFT_CLIENT_ID=<Application (client) ID from Step 1>
MICROSOFT_CLIENT_SECRET=<Value from Step 2>
MICROSOFT_TENANT_ID=common
# Use "common" for multi-tenant (personal + work accounts).
# Replace with your specific tenant ID for org-only access.
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/v1/auth/microsoft/callback
```

---

## Step 6 — Run the OAuth Flow

With the backend running:

1. Call `GET /api/v1/auth/microsoft` with a valid Bearer token — the response contains a Microsoft authorization URL
2. Open the URL in a browser and sign in with the Microsoft account
3. Microsoft redirects back to `MICROSOFT_REDIRECT_URI` — the backend stores the token at `tokens/outlook_user_<id>.json`
4. Register as a provider:

```http
PATCH /api/v1/user/users/me/calendar-setup
Authorization: Bearer <your-token>
Content-Type: application/json

{ "calendar_provider": "outlook" }
```

---

## Troubleshooting

**"AADSTS50011: The redirect URI does not match"**
The redirect URI in your `.env` must exactly match one registered in Step 1/4 — including `http` vs `https` and any trailing slashes.

**"AADSTS65001: The user or administrator has not consented"**
For work accounts, an admin must grant consent. Click **Grant admin consent** in Step 3, or ask your IT admin.

**"invalid_client" error**
The client secret may have expired. Rotate it in Azure (Step 2) and update your `.env`.

**Tokens expiring / Outlook keeps disconnecting**
Microsoft refresh tokens for personal accounts expire after 90 days of inactivity. The user needs to re-run the OAuth flow. For work accounts, token lifetime is controlled by the tenant policy.
