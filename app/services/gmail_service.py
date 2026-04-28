import base64
import glob
import json
import logging
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

from app.schemas.detection import EmailInput

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
    "https://www.googleapis.com/auth/calendar",  # write events for one-click calendar
    "https://www.googleapis.com/auth/tasks",      # create tasks after confirming a meeting
]

TOKENS_DIR = "tokens"
logger = logging.getLogger(__name__)


def get_token_path_for_user(user_id: int) -> str:
    """Return the token file path for an app user_id (API uses this for fetch)."""
    if not os.path.exists(TOKENS_DIR):
        os.makedirs(TOKENS_DIR)
    return os.path.join(TOKENS_DIR, f"gmail_user_{user_id}.json")


def _decode_body(data: str | None) -> str:
    if not data:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(data.encode("ASCII"))
        return decoded.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_body_from_payload(payload: dict[str, Any], snippet_fallback: str = "") -> str:
    """Extract full body from Gmail message payload (body or parts)."""
    body = payload.get("body", {})
    if body.get("data"):
        return _decode_body(body["data"])

    parts = payload.get("parts") or []
    text_plain: str | None = None
    text_html: str | None = None
    for part in parts:
        mime = (part.get("mimeType") or "").lower()
        part_body = part.get("body") or {}
        if not part_body.get("data"):
            continue
        decoded = _decode_body(part_body["data"])
        if mime == "text/plain":
            text_plain = decoded
        elif mime == "text/html" and text_html is None:
            text_html = decoded
    if text_plain:
        return text_plain
    if text_html:
        return text_html
    return snippet_fallback


class GmailService:
    def __init__(self, credentials_path: str = "credentials.json"):
        self.credentials_path = credentials_path
        self.creds: Credentials | None = None
        self.service: Resource | None = None
        self.current_email: str | None = None

        if not os.path.exists(TOKENS_DIR):
            os.makedirs(TOKENS_DIR)

    def list_registered_accounts(self) -> list[str]:
        """Scans the tokens directory and returns a list of registered email addresses (legacy gmail_*.json)."""
        token_files = glob.glob(os.path.join(TOKENS_DIR, "gmail_*.json"))
        emails = []
        for path in token_files:
            filename = os.path.basename(path)
            if filename.startswith("gmail_user_"):
                continue
            email = filename.replace("gmail_", "").replace(".json", "")
            emails.append(email)
        return emails

    def get_token_path_for_user(self, user_id: int) -> str:
        return get_token_path_for_user(user_id)

    def authenticate_for_user(self, user_id: int) -> bool:
        """Load token for app user_id, refresh if expired, build Gmail service. Returns True if token exists and is valid."""
        token_path = get_token_path_for_user(user_id)
        if not os.path.exists(token_path):
            return False
        try:
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(self.creds.to_json())
            self.service = build("gmail", "v1", credentials=self.creds)
            with open(token_path) as f:
                data = json.load(f)
            self.current_email = data.get("gmail_email") or data.get("client_id") or ""
            return True
        except Exception:
            logger.exception("Failed to authenticate stored Gmail token for user_id=%s", user_id)
            return False

    def authenticate_existing_account(self, email: str) -> bool:
        """Authenticates using an existing token for the given email (legacy)."""
        token_path = os.path.join(TOKENS_DIR, f"gmail_{email}.json")
        if not os.path.exists(token_path):
            return False
        try:
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(self.creds.to_json())
            self.service = build("gmail", "v1", credentials=self.creds)
            self.current_email = email
            return True
        except Exception:
            return False

    def authenticate_new_account(self) -> str | None:
        """Starts a new OAuth flow, saves the token with the email address, and returns the email."""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file not found at: {self.credentials_path}")
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
        self.creds = flow.run_local_server(port=0)
        service = build("oauth2", "v2", credentials=self.creds)
        user_info = service.userinfo().get().execute()
        email = user_info.get("email")
        if not email:
            raise Exception("Could not retrieve email address from user info.")
        email_str = str(email)
        token_path = os.path.join(TOKENS_DIR, f"gmail_{email_str}.json")
        with open(token_path, "w") as token:
            token.write(self.creds.to_json())
        self.service = build("gmail", "v1", credentials=self.creds)
        self.current_email = email_str
        return email_str

    def save_token_for_user(self, user_id: int, creds: Credentials, gmail_email: str | None = None) -> None:
        """Save token and optional gmail_email for an app user (e.g. from OAuth callback)."""
        token_path = get_token_path_for_user(user_id)
        data = json.loads(creds.to_json())
        if gmail_email:
            data["gmail_email"] = gmail_email
        with open(token_path, "w") as f:
            json.dump(data, f, indent=2)

    def fetch_email_page(
        self, page_token: str | None = None, limit: int = 50
    ) -> tuple[list[dict[str, str]], str | None]:
        """
        Fetch one page of emails using a single batch request.
        Returns (email_list, next_page_token). Each email has subject/sender/date/snippet.
        """
        if not self.service:
            return [], None
        try:
            kwargs: dict = {"userId": "me", "maxResults": limit}
            if page_token:
                kwargs["pageToken"] = page_token
            list_result = self.service.users().messages().list(**kwargs).execute()
            stubs = list_result.get("messages", [])
            next_token: str | None = list_result.get("nextPageToken")
            if not stubs:
                return [], next_token

            results_map: dict = {}

            def _on_response(request_id: str, response: Any, exception: Any) -> None:
                if exception is None:
                    results_map[request_id] = response

            batch = self.service.new_batch_http_request(callback=_on_response)
            for stub in stubs:
                batch.add(
                    self.service.users().messages().get(
                        userId="me",
                        id=stub["id"],
                        format="full",
                        fields="id,snippet,payload/headers",
                    ),
                    request_id=stub["id"],
                )
            batch.execute()

            email_data: list[dict[str, str]] = []
            for stub in stubs:
                msg = results_map.get(stub["id"])
                if not msg:
                    continue
                headers: list[dict[str, Any]] = msg.get("payload", {}).get("headers", [])
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "")
                snippet = msg.get("snippet", "")
                email_data.append({
                    "subject": subject,
                    "sender": sender,
                    "date": date,
                    "body": snippet,
                    "message_id": stub["id"],
                })
            return email_data, next_token
        except Exception:
            logger.exception("Failed to fetch Gmail email page for account=%s", self.current_email or "unknown")
            return [], None

    def fetch_email_body(self, message_id: str) -> str:
        """Fetch the full body of a single Gmail email by message_id."""
        if not self.service:
            return ""
        try:
            msg = self.service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
            payload = msg.get("payload", {})
            snippet = msg.get("snippet", "")
            return _extract_body_from_payload(payload, snippet)
        except Exception:
            logger.exception("Failed to fetch Gmail email body for message_id=%s", message_id)
            return ""

    def fetch_recent_emails(self, n: int | None = None) -> list[dict[str, str]]:
        """Fetch emails with full body. n=None fetches all (up to Gmail API limits via pagination)."""
        if not self.service:
            raise RuntimeError("Gmail service is not initialized.")
        try:
            # Collect message stubs via paginated list (Gmail max per page is 500)
            message_stubs: list[dict] = []
            page_token: str | None = None
            while True:
                kwargs: dict = {"userId": "me", "maxResults": 500}
                if page_token:
                    kwargs["pageToken"] = page_token
                results = self.service.users().messages().list(**kwargs).execute()
                stubs = results.get("messages", [])
                message_stubs.extend(stubs)
                page_token = results.get("nextPageToken")
                if not page_token or (n is not None and len(message_stubs) >= n):
                    break

            if n is not None:
                message_stubs = message_stubs[:n]

            if not message_stubs:
                return []

            email_data = []
            for message in message_stubs:
                msg = self.service.users().messages().get(
                    userId="me", id=message["id"], format="full"
                ).execute()
                payload = msg.get("payload", {})
                headers: list[dict[str, Any]] = payload.get("headers", [])
                snippet: str = msg.get("snippet", "")
                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "Unknown Date")
                body = _extract_body_from_payload(payload, snippet)
                message_id = msg.get("id", "")
                email_data.append({
                    "subject": subject,
                    "body": body,
                    "message_id": message_id,
                    "sender": sender,
                    "date": date,
                })
            return email_data
        except Exception:
            logger.exception("Failed to fetch Gmail emails for account=%s", self.current_email or "unknown")
            return []

    def fetch_recent_emails_as_inputs(self, n: int | None = None) -> list[EmailInput]:
        """Fetch emails and return as list[EmailInput] for detection."""
        raw = self.fetch_recent_emails(n=n)
        return [
            EmailInput(subject=r["subject"], body=r["body"], message_id=r["message_id"])
            for r in raw
        ]


def fetch_recent_emails_as_inputs_for_user(user_id: int, n: int | None = None) -> list[EmailInput]:
    """Load token for user_id, fetch recent emails, return list[EmailInput]. Returns [] if no token or fetch fails."""
    svc = GmailService()
    if not svc.authenticate_for_user(user_id):
        return []
    return svc.fetch_recent_emails_as_inputs(n=n)
