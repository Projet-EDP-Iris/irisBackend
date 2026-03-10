import glob
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import Resource, build

# Added userinfo.email to scopes to get the email address of the authenticated user
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

TOKENS_DIR = "tokens"


class GmailService:
    def __init__(self, credentials_path: str = "credentials.json"):
        self.credentials_path = credentials_path
        self.creds: Credentials | None = None
        self.service: Resource | None = None
        self.current_email: str | None = None

        if not os.path.exists(TOKENS_DIR):
            os.makedirs(TOKENS_DIR)

    def list_registered_accounts(self) -> list[str]:
        """Scans the tokens directory and returns a list of registered email addresses."""
        token_files = glob.glob(os.path.join(TOKENS_DIR, "gmail_*.json"))
        emails = []
        for path in token_files:
            filename = os.path.basename(path)
            # Filename format: gmail_{email}.json
            email = filename.replace("gmail_", "").replace(".json", "")
            emails.append(email)
        return emails

    def authenticate_existing_account(self, email: str) -> bool:
        """Authenticates using an existing token for the given email."""
        token_path = os.path.join(TOKENS_DIR, f"gmail_{email}.json")

        if not os.path.exists(token_path):
            print(f"Token not found for {email}")
            return False

        try:
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)

            # Refresh if expired
            if self.creds and self.creds.expired and self.creds.refresh_token:
                print(f"Refreshing token for {email}...")
                self.creds.refresh(Request())
                # Save refreshed token
                with open(token_path, "w") as token:
                    token.write(self.creds.to_json())

            self.service = build("gmail", "v1", credentials=self.creds)
            self.current_email = email
            print(f"Successfully authenticated as {email}")
            return True
        except Exception as e:
            print(f"Error authenticating {email}: {e}")
            return False

    def authenticate_new_account(self) -> str | None:
        """Starts a new OAuth flow, saves the token with the email address, and returns the email."""
        print("Starting new OAuth flow...")
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file not found at: {self.credentials_path}")

        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)

        # Run local server
        self.creds = flow.run_local_server(port=0)

        # Build service temporarily to get user info
        service = build("oauth2", "v2", credentials=self.creds)
        user_info = service.userinfo().get().execute()
        email = user_info.get("email")

        if not email:
            raise Exception("Could not retrieve email address from user info.")

        print(f"Authenticated as: {email}")

        # Save token with email in filename
        token_path = os.path.join(TOKENS_DIR, f"gmail_{email}.json")
        with open(token_path, "w") as token:
            token.write(self.creds.to_json())

        # Initialize Gmail service
        self.service = build("gmail", "v1", credentials=self.creds)
        self.current_email = email

        return email

    def fetch_recent_emails(self, n: int = 5) -> list[dict[str, str]]:
        if not self.service:
            raise RuntimeError("Gmail service is not initialized.")

        try:
            results = self.service.users().messages().list(userId="me", maxResults=n).execute()
            messages = results.get("messages", [])

            email_data = []
            if not messages:
                print("No messages found.")
                return []

            print(f"Fetching {len(messages)} emails for {self.current_email}...")
            for message in messages:
                msg = self.service.users().messages().get(userId="me", id=message["id"]).execute()

                payload = msg.get("payload", {})
                headers: list[dict[str, Any]] = payload.get("headers", [])
                snippet: str = msg.get("snippet", "")

                subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
                sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
                date = next((h["value"] for h in headers if h["name"] == "Date"), "Unknown Date")

                email_data.append(
                    {"sender": sender, "subject": subject, "date": date, "snippet": snippet}
                )

            return email_data

        except Exception as e:
            print(f"An error occurred while fetching emails: {e}")
            return []
