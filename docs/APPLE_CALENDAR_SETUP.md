# Apple Calendar Setup (iCloud CalDAV + App Password)

Iris connects to Apple Calendar via CalDAV using an iCloud App Password. Apple ID's two-factor authentication means the user's actual password cannot be used — an App Password is a separate, single-purpose credential generated from Apple's website.

---

## Prerequisites

- An Apple ID with two-factor authentication enabled
- An iCloud account with at least one calendar

---

## Step 1 — Generate an App Password

1. Go to [appleid.apple.com](https://appleid.apple.com) and sign in
2. Under **Sign-In and Security**, click **App-Specific Passwords**
3. Click **+** (Generate an App-Specific Password)
4. Give it a label (e.g. `Iris Backend`)
5. Copy the generated password — it looks like `xxxx-xxxx-xxxx-xxxx`

> You cannot view this password again after closing the dialog. Store it somewhere safe.

---

## Step 2 — Generate the Encryption Key

Apple passwords are Fernet-encrypted before being stored in the database. You need to generate a key once and add it to your `.env`.

Run this in the project directory:

```bash
poetry run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output and add it to your `.env`:

```env
SECRET_ENCRYPTION_KEY=<paste-the-key-here>
```

> **Important:** Generate this key once and never change it after your first user stores an Apple password. Changing the key makes all stored passwords unreadable.

---

## Step 3 — Connect Apple Calendar via the API

Call the calendar setup endpoint with the iCloud email address and App Password:

```http
PATCH /api/v1/user/users/me/calendar-setup
Authorization: Bearer <your-token>
Content-Type: application/json

{
  "calendar_provider": "apple",
  "apple_caldav_user": "yourname@icloud.com",
  "apple_caldav_password": "xxxx-xxxx-xxxx-xxxx"
}
```

The API immediately tests the CalDAV connection. If the credentials are wrong, it returns `400` and does not store anything. On success, the App Password is encrypted and stored — the plain text is never persisted.

---

## Step 4 — Confirm a Calendar Event

Once connected, use the standard confirm endpoint:

```http
POST /api/v1/calendar/confirm/{email_id}
Authorization: Bearer <your-token>
Content-Type: application/json

{ "slot_index": 0 }
```

The event is created in the first available iCloud calendar.

---

## Disconnecting

```http
DELETE /api/v1/user/users/me/calendar-disconnect?provider=apple
Authorization: Bearer <your-token>
```

This removes the stored credentials from the database.

---

## Troubleshooting

**"CalDAV connection failed"**
- Confirm the App Password was copied correctly (no extra spaces)
- Confirm the iCloud email is the one associated with the Apple ID where you created the password
- Confirm two-factor authentication is enabled on the Apple ID (required for App Passwords)

**"No iCloud calendars found"**
The Apple ID must have at least one calendar in iCloud. Open the Calendar app on any Apple device, create a calendar under "iCloud", then retry.

**App Password revoked**
Apple revokes App Passwords if you change your Apple ID password. Generate a new one (Step 1) and call the calendar-setup endpoint again to update the stored credentials.
