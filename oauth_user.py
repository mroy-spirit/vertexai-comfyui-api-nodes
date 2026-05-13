import logging
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)

_oauth_email: Optional[str] = None


def get_oauth_email() -> Optional[str]:
    return _oauth_email


def capture_email_from_request(request: web.Request) -> Optional[str]:
    """
    Capture the X-Auth-Request-Email header (set by oauth2-proxy) into the
    module-level cache. Safe to call from any handler — returns the current
    cached email regardless of whether the header was present.
    """
    global _oauth_email
    header_email = request.headers.get("X-Auth-Request-Email")
    if header_email:
        if header_email != _oauth_email:
            logger.info(f"OAuth user identified: {header_email}")
        _oauth_email = header_email
    return _oauth_email


def register(prompt_server) -> None:
    @prompt_server.routes.get("/vertexai/whoami")
    async def whoami(request: web.Request) -> web.Response:
        header_email = request.headers.get("X-Auth-Request-Email")
        capture_email_from_request(request)
        return web.json_response({
            "email": _oauth_email,
            "header_received": header_email,
        })
