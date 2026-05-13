import json
import logging

logger = logging.getLogger(__name__)

_UNSET = object()
_cached_email: object = _UNSET


def _resolve_auth_email() -> str | None:
    """Retrieve the email address from the active ADC credentials (cached after first call)."""
    try:
        import google.auth
        import google.auth.transport.requests
        import requests as _req

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())

        # Service accounts and Compute Engine credentials expose this directly
        if hasattr(creds, "service_account_email") and creds.service_account_email:
            return creds.service_account_email

        # User OAuth2 credentials: ask the tokeninfo endpoint
        token = getattr(creds, "token", None)
        if token:
            resp = _req.get(
                "https://www.googleapis.com/oauth2/v1/tokeninfo",
                params={"access_token": token},
                timeout=5,
            )
            if resp.ok:
                return resp.json().get("email")
    except Exception as exc:
        logger.debug(f"Could not resolve authenticated email: {exc}")
    return None


def get_auth_email() -> str | None:
    # Prefer the OAuth2 user email captured from the reverse proxy (nginx + oauth2-proxy)
    try:
        from .oauth_user import get_oauth_email
        email = get_oauth_email()
        if email:
            return email
    except Exception:
        pass
    # Fall back to ADC credentials (service account on GCE)
    global _cached_email
    if _cached_email is _UNSET:
        _cached_email = _resolve_auth_email()
    return _cached_email


def default_labels_json() -> str:
    """Return the default labels as a JSON string, for use as widget default values."""
    defaults: dict = {"app": "comfyui"}
    email = get_auth_email()
    if email:
        defaults["user"] = email
    return json.dumps(defaults)


def build_labels(labels_json: str) -> dict:
    """
    Build a labels dict for Cloud Logging / BigQuery tracking.

    Always includes:
      - app = "comfyui"
      - user = authenticated email (if resolvable from ADC)

    User-provided labels_json is merged on top and can override defaults.
    """
    user_labels: dict = {}
    if labels_json and labels_json.strip():
        try:
            parsed = json.loads(labels_json)
            if isinstance(parsed, dict):
                user_labels = parsed
            else:
                logger.warning("labels_json must be a JSON object; user labels ignored.")
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid labels_json ({exc}); user labels ignored.")

    defaults: dict = {"app": "comfyui"}
    email = get_auth_email()
    if email:
        defaults["user"] = email

    return {**defaults, **user_labels}
