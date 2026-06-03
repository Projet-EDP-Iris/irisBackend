import uuid
from datetime import UTC, datetime

import caldav

from app.core.encryption import decrypt

APPLE_CALDAV_URL = "https://caldav.icloud.com"


def _connect(apple_user: str, plain_password: str):
    """Return (client, principal, calendars). Raises on auth failure."""
    client = caldav.DAVClient(
        url=APPLE_CALDAV_URL,
        username=apple_user,
        password=plain_password,
    )
    principal = client.principal()
    calendars = principal.calendars()
    return client, principal, calendars


def _fmt_utc(dt: datetime) -> str:
    """Format datetime as compact UTC iCalendar string (YYYYMMDDTHHMMSSZ)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def test_connection(apple_user: str, encrypted_password: str) -> None:
    """
    Validate that the Apple ID + App-Specific Password can reach iCloud CalDAV.

    Raises RuntimeError or a caldav exception if authentication fails or if the
    account has no calendars. Call this before persisting credentials.

    App-Specific Passwords are generated at appleid.apple.com → Security →
    App-Specific Passwords. They look like xxxx-xxxx-xxxx-xxxx and require
    2-Factor Authentication to be enabled on the Apple ID.
    """
    plain_password = decrypt(encrypted_password)
    _, _, calendars = _connect(apple_user, plain_password)
    if not calendars:
        raise RuntimeError(f"No iCloud calendars found for {apple_user}")


def list_calendars(apple_user: str, encrypted_password: str) -> list[dict]:
    """
    Return a list of the user's iCloud calendars.

    Each entry: {"name": str, "url": str}
    """
    plain_password = decrypt(encrypted_password)
    _, _, calendars = _connect(apple_user, plain_password)
    return [{"name": cal.name, "url": str(cal.url)} for cal in calendars]


def create_apple_calendar_event(
    apple_user: str,
    encrypted_password: str,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
    timezone: str = "UTC",
) -> str:
    """
    Creates an event on the user's primary iCloud Calendar via CalDAV.

    apple_user: the user's Apple ID email (e.g. dan@icloud.com)
    encrypted_password: the Fernet-encrypted App Password stored in the DB.
        App Passwords are generated at appleid.apple.com → Security → App Passwords.
        They look like xxxx-xxxx-xxxx-xxxx and bypass 2FA for third-party apps.

    Returns the event UID (a UUID string) — store this in Email.calendar_event_id
    so the event can be updated or deleted later.

    The iCalendar (.ics) format used here is the universal calendar standard,
    the same format used when you receive a meeting invite by email.
    """
    plain_password = decrypt(encrypted_password)
    _, _, calendars = _connect(apple_user, plain_password)
    if not calendars:
        raise RuntimeError(f"No iCloud calendars found for {apple_user}")

    calendar = calendars[0]
    event_uid = str(uuid.uuid4())
    dtstamp = _fmt_utc(datetime.now(UTC))

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Iris AI//Calendar//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{event_uid}\r\n"
        f"DTSTAMP:{dtstamp}\r\n"
        f"DTSTART:{_fmt_utc(start_time)}\r\n"
        f"DTEND:{_fmt_utc(end_time)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description or ''}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    calendar.save_event(ics)
    return event_uid


def update_apple_calendar_event(
    apple_user: str,
    encrypted_password: str,
    uid: str,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
) -> None:
    """
    Update an existing iCloud Calendar event identified by its UID.

    uid: the UUID string returned by create_apple_calendar_event().
    Raises RuntimeError if the event is not found in any of the user's calendars.
    """
    plain_password = decrypt(encrypted_password)
    _, _, calendars = _connect(apple_user, plain_password)

    for calendar in calendars:
        try:
            results = calendar.search(uid=uid)
            if results:
                event = results[0]
                vevent = event.vobject_instance.vevent
                vevent.summary.value = summary
                vevent.dtstart.value = datetime.strptime(_fmt_utc(start_time), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                vevent.dtend.value = datetime.strptime(_fmt_utc(end_time), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
                if description is not None:
                    if hasattr(vevent, "description"):
                        vevent.description.value = description
                    else:
                        vevent.add("description").value = description
                event.save()
                return
        except Exception:  # noqa: BLE001
            continue

    raise RuntimeError(f"Event UID {uid!r} not found in any iCloud calendar for {apple_user}")


def delete_apple_calendar_event(
    apple_user: str,
    encrypted_password: str,
    uid: str,
) -> None:
    """
    Delete an iCloud Calendar event by its UID.

    uid: the UUID string returned by create_apple_calendar_event().
    Raises RuntimeError if the event is not found.
    """
    plain_password = decrypt(encrypted_password)
    _, _, calendars = _connect(apple_user, plain_password)

    for calendar in calendars:
        try:
            results = calendar.search(uid=uid)
            if results:
                results[0].delete()
                return
        except Exception:  # noqa: BLE001
            continue

    raise RuntimeError(f"Event UID {uid!r} not found in any iCloud calendar for {apple_user}")
