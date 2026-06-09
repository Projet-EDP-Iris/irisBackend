# Email Reply Feature

## Overview

Users can reply directly to emails from within Iris. The flow is:

1. Open an email and click **Répondre** — Iris generates 3 AI-suggested reply variants (Formel, Amical, Court)
2. Click **Utiliser →** on any variant to load it into the reply composer
3. Edit the text freely, optionally attach files
4. Click **Envoyer la réponse** — the reply is sent via Resend

The reply is delivered to the original sender's email address. If the `rfc_message_id` was captured (see below), the reply appears as a thread in the recipient's mail client.

---

## Email Threading

### The problem

Email threading (grouping replies under the original email) requires the RFC 2822 `Message-ID` header — a globally unique identifier that looks like:

```
<CABcdef1234@mail.gmail.com>
```

This is **not** the same as the Gmail API's internal message `id` (e.g. `18a2b3c4d5e6f7g8`) or Outlook's Graph API `id`. Those are provider-specific identifiers for API calls, not email headers.

### How Iris captures it

| Provider | Source |
|----------|--------|
| Gmail | `payload.headers` array — look for `name: "Message-ID"` |
| Outlook | Microsoft Graph `internetMessageId` field |

Both are extracted when emails are fetched and stored in the `emails.rfc_message_id` column.

### How threading is applied on send

When `POST /api/v1/emails/reply/{email_id}` is called, `resend_service.send_reply()` sets two RFC 2822 headers:

```
In-Reply-To: <original-message-id>
References:  <original-message-id>
```

These tell the recipient's mail client (Gmail, Outlook, Apple Mail, etc.) to group this message under the original thread.

**If `rfc_message_id` is null** (emails fetched before this feature was added), the reply still sends — it just arrives as a standalone email rather than a thread reply. On the next fetch, the `rfc_message_id` backfill logic in `_upsert_email_items` will populate it.

---

## Resend Setup

### 1. Create an account

Sign up at [resend.com](https://resend.com) and create an API key from the dashboard.

### 2. Verify a sending domain

Resend requires you to send from a domain you own and have verified via DNS. Go to **Domains** in the Resend dashboard and add your domain. You'll need to add:
- An SPF TXT record
- A DKIM TXT record
- (Optional) A DMARC record

### 3. Configure environment variables

Add to your `.env` (backend):

```env
RESEND_API_KEY=re_your_api_key_here
RESEND_FROM_EMAIL=reply@yourdomain.com
```

`RESEND_FROM_EMAIL` must be an address on a domain you've verified with Resend.

---

## Known Limitation: Sender Address

Replies are sent **from `RESEND_FROM_EMAIL`** (your verified Resend domain), not from the user's personal Gmail or Outlook address. The recipient will see something like:

```
From: reply@iris-app.com
```

This is a fundamental constraint of using Resend as the outbound transport. The user's email provider (Gmail/Outlook) would need to explicitly grant send-as permissions for Iris to send on their behalf.

**Future enhancement:** Use the Gmail API's `users.messages.send` with the user's own OAuth token to send replies directly from the user's address. This would require adding the `https://www.googleapis.com/auth/gmail.send` scope to the Gmail OAuth flow.

---

## API Reference

### `POST /api/v1/emails/reply/{email_id}`

Send a reply to the original sender of the stored email.

**Content-Type:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reply_text` | string (form field) | Yes | The reply body |
| `attachments` | file (form field, repeatable) | No | Files to attach |

**Response:**

```json
{ "status": "sent", "resend_id": "re_abc123" }
```

**Error codes:**
- `404` — Email not found or belongs to another user
- `400` — Original sender address not stored
- `503` — `RESEND_API_KEY` not configured
- `502` — Resend API returned an error

---

## File Layout

| File | Role |
|------|------|
| `app/models/email.py` | `rfc_message_id` column |
| `app/schemas/email.py` | `EmailItem.rfc_message_id` field |
| `app/services/gmail_service.py` | Extracts `Message-ID` header from Gmail API payload |
| `app/services/outlook_email_service.py` | Extracts `internetMessageId` from Graph API |
| `app/api/endpoints/emails.py` | `_upsert_email_items` persists `rfc_message_id`; reply endpoint |
| `app/services/resend_service.py` | `send_reply()` — Resend API call with threading headers |
| `irisFrontendApp/src/pages/emails.tsx` | `ReplyVariantsView`, `ReplyComposer`, `EmailPanel` |

---

## Testing

1. Set `RESEND_API_KEY` and `RESEND_FROM_EMAIL` in `.env`
2. Start the backend: `poetry run uvicorn app.main:app --reload`
3. Fetch emails — check DB: `SELECT message_id, rfc_message_id FROM emails LIMIT 5;` — `rfc_message_id` should be populated
4. Open an email in the UI, click **Répondre**, select a variant with **Utiliser →**
5. Edit the text, optionally attach a file, click **Envoyer la réponse**
6. Check the Resend dashboard for delivery confirmation
7. In the recipient's inbox, verify the reply appears threaded under the original email
