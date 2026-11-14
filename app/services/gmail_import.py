"""Read-only Gmail access for previewing SEEK Grad alert messages."""

from __future__ import annotations

import logging
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailSetupError(RuntimeError):
    """Gmail OAuth is not configured or could not be authorized."""


def gmail_status(client_file: str, token_file: str) -> dict[str, object]:
    client_path = Path(client_file).expanduser()
    token_path = Path(token_file).expanduser()
    return {
        "client_configured": client_path.is_file(),
        "connected": token_path.is_file(),
    }


def authorize_gmail(client_file: str, token_file: str) -> None:
    """Run Google's installed-app browser consent flow and save credentials locally."""
    path = Path(client_file).expanduser()
    if not path.is_file():
        raise GmailSetupError(
            f"OAuth client file not found at {path}. Add your Google Desktop app JSON there."
        )
    token_path = Path(token_file).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(path), [GMAIL_READONLY_SCOPE])
        credentials = flow.run_local_server(port=0, open_browser=True, access_type="offline")
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    except Exception as exc:
        logger.warning("Gmail authorization did not complete (%s)", type(exc).__name__)
        raise GmailSetupError(
            "Gmail authorization did not complete. Check the OAuth client configuration "
            "and try again."
        ) from exc


def _credentials(client_file: str, token_file: str) -> Credentials:
    token_path = Path(token_file).expanduser()
    if not token_path.is_file():
        raise GmailSetupError("Gmail is not connected yet. Choose Connect Gmail first.")
    try:
        credentials = Credentials.from_authorized_user_file(str(token_path), [GMAIL_READONLY_SCOPE])
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_path.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise GmailSetupError("Gmail access expired. Connect Gmail again.")
        return credentials
    except GmailSetupError:
        raise
    except Exception as exc:
        logger.warning("Stored Gmail authorization is unusable (%s)", type(exc).__name__)
        raise GmailSetupError(
            "Stored Gmail authorization is unusable. Connect Gmail again."
        ) from exc


def read_seek_alerts(
    client_file: str, token_file: str, label: str, query: str, limit: int = 30
) -> list[dict[str, str]]:
    """Read recent matching raw messages without modifying the Gmail mailbox."""
    if not label.strip():
        raise GmailSetupError("Set GMAIL_SEEK_LABEL to the Gmail label containing SEEK alerts.")
    credentials = _credentials(client_file, token_file)
    search = f'label:"{label.strip()}" {query.strip()}'.strip()
    try:
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        listed = (
            service.users()
            .messages()
            .list(userId="me", q=search, maxResults=min(max(limit, 1), 100))
            .execute()
        )
        output: list[dict[str, str]] = []
        for item in listed.get("messages", []):
            message = (
                service.users().messages().get(userId="me", id=item["id"], format="raw").execute()
            )
            import base64

            raw = base64.urlsafe_b64decode(message["raw"] + "==").decode("utf-8", errors="replace")
            output.append({"id": item["id"], "raw": raw})
        return output
    except HttpError as exc:
        logger.warning("Gmail API request failed with HTTP %s", exc.resp.status)
        raise GmailSetupError(
            "Gmail could not be searched. Check the label, permissions, and Gmail API setup."
        ) from exc


def read_prosple_alerts(
    client_file: str, token_file: str, label: str = "", query: str = "", limit: int = 30
) -> list[dict[str, str]]:
    """Read recent Prosple alert messages from Gmail without modifying the mailbox."""
    credentials = _credentials(client_file, token_file)
    default_query = (
        "newer_than:30d "
        '{from:notifications@prosple.com from:richard@prosple.com "your pathway starts here"}'
    )
    search = " ".join(
        part
        for part in (
            f'label:"{label.strip()}"' if label.strip() else "",
            query.strip() or default_query,
        )
        if part
    )
    try:
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        listed = (
            service.users()
            .messages()
            .list(userId="me", q=search, maxResults=min(max(limit, 1), 100))
            .execute()
        )
        output: list[dict[str, str]] = []
        for item in listed.get("messages", []):
            message = (
                service.users().messages().get(userId="me", id=item["id"], format="raw").execute()
            )
            import base64

            raw = base64.urlsafe_b64decode(message["raw"] + "==").decode("utf-8", errors="replace")
            output.append({"id": item["id"], "raw": raw})
        return output
    except HttpError as exc:
        logger.warning("Gmail API request failed with HTTP %s", exc.resp.status)
        raise GmailSetupError(
            "Gmail could not be searched for Prosple alerts. Check the label, permissions, "
            "and Gmail API setup."
        ) from exc
