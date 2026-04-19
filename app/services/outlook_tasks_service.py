from datetime import datetime

import httpx

from app.services.microsoft_oauth_service import get_valid_token

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _get_default_tasklist_id(access_token: str) -> str:
    """Return the ID of the user's default Microsoft To Do task list."""
    resp = httpx.get(
        f"{_GRAPH_BASE}/me/todo/lists",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    lists = resp.json().get("value", [])
    # Microsoft always provides at least one list ("Tasks" / "Tâches")
    if not lists:
        raise RuntimeError("No task lists found in Microsoft To Do for this user")
    # Prefer the list flagged as default (isOwner + wellknownListName == "defaultList")
    for lst in lists:
        if lst.get("wellknownListName") == "defaultList":
            return lst["id"]
    return lists[0]["id"]


def create_outlook_task(
    user_id: int,
    title: str,
    due: datetime | None = None,
    notes: str | None = None,
) -> str:
    """
    Creates a task in the user's default Microsoft To Do list via Graph API.

    Uses the stored OAuth token from microsoft_oauth_service.
    Returns the created task ID.
    """
    access_token = get_valid_token(user_id)
    list_id = _get_default_tasklist_id(access_token)

    task_body: dict = {
        "title": title,
        "status": "notStarted",
    }
    if notes:
        task_body["body"] = {"content": notes, "contentType": "text"}
    if due:
        # Graph API expects ISO 8601 with timezone in dateTimeTimeZone format
        task_body["dueDateTime"] = {
            "dateTime": due.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
            "timeZone": "UTC",
        }

    resp = httpx.post(
        f"{_GRAPH_BASE}/me/todo/lists/{list_id}/tasks",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=task_body,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]
