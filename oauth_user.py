import logging
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)

# Last OAuth2 user email captured from the reverse proxy.
# Good enough for single-user ComfyUI; for multi-user setups this would need
# to be keyed per-session/client-id.
_oauth_email: Optional[str] = None


def get_oauth_email() -> Optional[str]:
    return _oauth_email


def register(prompt_server) -> None:
    @prompt_server.routes.get("/vertexai/whoami")
    async def whoami(request: web.Request) -> web.Response:
        global _oauth_email
        # oauth2-proxy sets this header on every authenticated request
        header_email = request.headers.get("X-Auth-Request-Email")
        if header_email:
            if header_email != _oauth_email:
                logger.info(f"OAuth user identified: {header_email}")
            _oauth_email = header_email
        return web.json_response({
            "email": _oauth_email,
            "header_received": header_email,  # None if header was absent
        })
