import glob
import os
import base64
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import Resource, build

# Scopes for Gmail readonly and user email 
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

TOKENS_DIR = "tokens"

class GmailService:
    def __init__(self, credentials_path: str = "credentials.json"):
        self.credentials_path = credentials_path
        # We'll use a local session-based approach or re-initialize per request for thread safety in FastAPI
        if not os.path.exists(TOKENS_DIR):
            os.makedirs(TOKENS_DIR)

    def _get_token_path(self, user_id: int) -> str:
        return os.path.join(TOKENS_DIR, f"gmail_user_{user_id}.json")

    def authenticate_for_user(self, user_id: int) -> Optional[Resource]:
        """Loads or refreshes the token for a specific user ID."""
        token_path = self._get_token_path(user_id)

        if not os.path.exists(token_path):
            return None

        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

            # Refresh if expired
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Save refreshed token
                with open(token_path, "w") as token:
                    token.write(creds.to_json())

            service = build("gmail", "v1", credentials=creds)
            return service
        except Exception as e:
            print(f"Error authenticating user {user_id}: {e}")
            return None

    def get_flow(self, redirect_uri: str) -> Flow:
        """Returns the OAuth flow object for starting/completing auth."""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file not found at: {self.credentials_path}")
        
        return Flow.from_client_secrets_file(
            self.credentials_path,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )

    def save_user_token(self, user_id: int, creds: Credentials):
        """Saves the credentials for a user."""
        token_path = self._get_token_path(user_id)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    def fetch_recent_emails(self, service: Resource, n: int = 10) -> List[Dict[str, Any]]:
        """Fetch n recent emails and decode them."""
        try:
            results = service.users().messages().list(userId="me", maxResults=n).execute()
            messages = results.get("messages", [])

            email_data = []
            if not messages:
                return []

            for message in messages:
                msg_id = message["id"]
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

                payload = msg.get("payload", {})
                headers: List[Dict[str, Any]] = payload.get("headers", [])
                snippet: str = msg.get("snippet", "")

                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "Unknown Date")

                # Extract body
                body = self._get_body(payload)

                email_data.append({
                    "message_id": msg_id,
                    "sender": sender,
                    "subject": subject,
                    "date": date,
                    "snippet": snippet,
                    "body": body
                })

            return email_data

        except Exception as e:
            print(f"An error occurred while fetching emails: {e}")
            return []

    def _get_body(self, payload: Dict[str, Any]) -> str:
        """Recursively search for body content, preferring plain text."""
        body = ""
        
        if "parts" in payload:
            # Multi-part message
            parts = payload["parts"]
            # Look for text/plain first
            for part in parts:
                if part["mimeType"] == "text/plain" and "data" in part["body"]:
                    return self._decode_base64(part["body"]["data"])
            
            # If no plain text, look for text/html
            for part in parts:
                if part["mimeType"] == "text/html" and "data" in part["body"]:
                    return self._decode_base64(part["body"]["data"])
            
            # Recursive check for nested parts
            for part in parts:
                if "parts" in part:
                    res = self._get_body(part)
                    if res:
                        return res
        else:
            # Single-part message
            if "data" in payload["body"]:
                return self._decode_base64(payload["body"]["data"])
        
        return body

    def _decode_base64(self, data: str) -> str:
        """Decode URL-safe base64 data."""
        try:
            decoded_bytes = base64.urlsafe_b64decode(data.encode("UTF-8"))
            return decoded_bytes.decode("UTF-8", errors="replace")
        except Exception:
            return ""

    def fetch_recent_emails_as_inputs(self, service: Resource, n: int = 10) -> List[Dict[str, Any]]:
        """Same as fetch_recent_emails but returns them as inputs for NLP tasks."""
        return self.fetch_recent_emails(service, n)

