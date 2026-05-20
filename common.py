import json
import logging
import sys
from typing import Optional

logger = logging.getLogger(__name__)


def log_event(payload: dict) -> None:
    """Write a structured JSON event directly to stdout.

    The Ops Agent on GCE detects JSON objects on individual stdout lines and
    ingests them as jsonPayload (not textPayload), making all fields—including
    `labels`—queryable as proper columns in a BigQuery Cloud Logging export.
    Python's standard logger prefixes lines with 'LEVEL:module:', which breaks
    JSON detection and forces textPayload, so we bypass it here.
    """
    print(json.dumps({"severity": "INFO", **payload}), file=sys.stdout, flush=True)

_UNSET = object()
_cached_email: object = _UNSET


def _resolve_auth_email() -> Optional[str]:
    """Retrieve the email address from the active ADC credentials (cached after first call)."""
    try:
        import google.auth
        import google.auth.transport.requests
        import requests as _req

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())

        if hasattr(creds, "service_account_email") and creds.service_account_email:
            return creds.service_account_email

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


def get_auth_email() -> Optional[str]:
    # Prefer OAuth2 user email captured from the reverse proxy (nginx + oauth2-proxy)
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


def build_labels(custom_label_key: str = "", custom_label_value: str = "") -> dict:
    """
    Build a labels dict for Cloud Logging / BigQuery tracking.

    Always sets (not overridable):
      - app = "comfyui"
      - user = OAuth2 email from reverse proxy, or ADC email as fallback

    Extra labels from the VertexAI settings panel (extra_labels JSON) are merged in.
    An optional per-node custom label can be added via custom_label_key/value.
    """
    result: dict = {}

    # Admin-configured extra labels from the settings panel
    try:
        from .vertexai_settings import get_settings
        raw = get_settings().get("extra_labels", "{}") or "{}"
        extra = json.loads(raw)
        if isinstance(extra, dict):
            result.update(extra)
    except Exception:
        pass

    # Per-node single custom label (both key and value must be non-empty)
    if custom_label_key and custom_label_key.strip() and custom_label_value:
        result[custom_label_key.strip()] = custom_label_value

    # System-reserved — always written last so they cannot be overridden
    result["app"] = "comfyui"
    email = get_auth_email()
    if email:
        result["user"] = email

    return result
