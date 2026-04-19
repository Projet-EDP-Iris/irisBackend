from datetime import datetime

from googleapiclient.discovery import build

from app.services.google_calendar_service import _load_creds_for_user


def create_google_task(
    user_id: int,
    title: str,
    due: datetime | None = None,
    notes: str | None = None,
) -> str:
    """
    Creates a task in the user's default Google Tasks list.

    Reuses the same OAuth credentials as Gmail and Calendar — no extra
    auth step needed as long as the `tasks` scope was granted.

    Returns the created task ID (store if you need to update/delete later).
    """
    creds = _load_creds_for_user(user_id)

    # Same build() pattern as Gmail and Calendar services
    service = build("tasks", "v1", credentials=creds)

    # Get the user's task lists and pick the first (default "@default" also works)
    lists_response = service.tasklists().list(maxResults=1).execute()
    items = lists_response.get("items", [])
    tasklist_id = items[0]["id"] if items else "@default"

    task_body: dict = {"title": title}
    if notes:
        task_body["notes"] = notes
    if due:
        # Google Tasks requires RFC 3339 format with a Z suffix
        task_body["due"] = due.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    created = (
        service.tasks()
        .insert(tasklist=tasklist_id, body=task_body)
        .execute()
    )
    return created["id"]
