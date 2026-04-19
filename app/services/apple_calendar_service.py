import uuid
from datetime import datetime, timezone as dt_timezone

import caldav

from app.core.encryption import decrypt


APPLE_CALDAV_URL = "https://caldav.icloud.com"


def create_apple_calendar_event(
    apple_user: str,
    encrypted_password: str,
    summary: str,
    start_time: datetime,
    end_time: datetime,
    description: str | None = None,
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

    # caldav.DAVClient manages the HTTPS connection with HTTP Basic Auth
    client = caldav.DAVClient(
        url=APPLE_CALDAV_URL,
        username=apple_user,
        password=plain_password,
    )

    # principal() is the user's CalDAV "account root"
    principal = client.principal()

    calendars = principal.calendars()
    if not calendars:
        raise RuntimeError(f"No iCloud calendars found for {apple_user}")

    # Use the first calendar (the user's primary/default calendar)
    calendar = calendars[0]

    event_uid = str(uuid.uuid4())

    # DTSTART/DTEND must be in compact UTC format: YYYYMMDDTHHMMSSZ
    def _fmt(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    dtstamp = _fmt(datetime.now(dt_timezone.utc))

    ics = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Iris AI//Calendar//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{event_uid}\r\n"
        f"DTSTAMP:{dtstamp}\r\n"
        f"DTSTART:{_fmt(start_time)}\r\n"
        f"DTEND:{_fmt(end_time)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{description or ''}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )

    calendar.save_event(ics)

    return event_uid
