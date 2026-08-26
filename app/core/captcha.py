import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """
    Validate a Cloudflare Turnstile token against the siteverify API.

    Returns True immediately if TURNSTILE_ENABLED is False (dev / test mode).
    Returns False (fail-closed) on network error or invalid token.
    """
    if not settings.TURNSTILE_ENABLED:
        return True
    if not settings.TURNSTILE_SECRET_KEY:
        # Comportement intentionnel : échappatoire de déploiement.
        # Permet d'activer TURNSTILE_ENABLED=true avant que la clé secrète
        # Cloudflare soit provisionnée (ex. : déploiement par étapes).
        # À NE PAS laisser ainsi en production finale.
        logger.warning("TURNSTILE_ENABLED=True but TURNSTILE_SECRET_KEY is not set — allowing request")
        return True

    payload: dict[str, str] = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(_SITEVERIFY_URL, data=payload, timeout=5.0)
        result: bool = resp.json().get("success", False)
        if not result:
            logger.warning("Turnstile rejected token (remote_ip=%s)", remote_ip)
        return result
    except Exception:
        logger.exception("Turnstile siteverify call failed — denying request")
        return False  # fail-closed: network error → block
