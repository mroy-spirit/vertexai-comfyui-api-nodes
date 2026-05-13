import json
import logging
import os
from pathlib import Path
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).parent / "vertexai-settings.json"

_DEFAULTS: dict = {
    "gcp_project": "",
    "gcp_location": "us-central1",
    "storage_uri": "gs://your-bucket/output/",
    "extra_labels": "{}",
    "sa_key_path": "",
}

_UNSET = object()
_cached_project_id: object = _UNSET
_cached_on_gce: object = _UNSET


def _read_stored() -> dict:
    """Read the raw stored settings file without applying any auto-detect
    transformations. Safe to call from helpers that themselves feed into
    get_settings() (avoids recursion)."""
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def is_on_gce() -> bool:
    """Detect whether we're running inside Google Compute Engine / Cloud Run by
    probing the metadata server. Cached for the process lifetime."""
    global _cached_on_gce
    if _cached_on_gce is not _UNSET:
        return _cached_on_gce  # type: ignore[return-value]

    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=1) as r:
            _cached_on_gce = (r.status == 200)
    except Exception:
        _cached_on_gce = False
    return _cached_on_gce  # type: ignore[return-value]


def _apply_sa_key_env() -> None:
    """If a SA key path is configured (and we're not on GCE), point
    GOOGLE_APPLICATION_CREDENTIALS at it so google.auth.default() picks it up.
    On GCE the env var is left alone — metadata server takes precedence."""
    if is_on_gce():
        return
    sa_path = _read_stored().get("sa_key_path", "") or ""
    sa_path = sa_path.strip()
    if sa_path and Path(sa_path).is_file():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path
        logger.info(f"VertexAI: GOOGLE_APPLICATION_CREDENTIALS set to {sa_path}")


def get_auth_status() -> dict:
    """Describe the current GCP-API authentication state for the Settings panel
    banner. This is distinct from oauth_user.get_oauth_email() (which is the
    reverse-proxy header used for the 'user' Cloud Logging label)."""
    on_gce = is_on_gce()
    sa_path = (_read_stored().get("sa_key_path", "") or "").strip()

    try:
        import google.auth
        creds, _ = google.auth.default()
        sa_email = getattr(creds, "service_account_email", None)
        if on_gce:
            method = "metadata server"
            account = sa_email or "GCE service account"
            message = f"✓ Running on GCE — metadata server authentication ({account})"
        elif sa_path:
            method = "service account key"
            account = sa_email or sa_path
            message = f"✓ Authenticated via service account key ({account})"
        else:
            method = "user credentials"
            account = "gcloud user credentials"
            message = f"✓ Authenticated via {account}"
        return {
            "on_gce": on_gce,
            "sa_key_configured": bool(sa_path),
            "ok": True,
            "method": method,
            "account": account,
            "message": message,
        }
    except Exception as exc:
        logger.debug(f"VertexAI auth_status: google.auth.default() failed: {exc}")
        return {
            "on_gce": on_gce,
            "sa_key_configured": bool(sa_path),
            "ok": False,
            "method": None,
            "account": None,
            "message": (
                "⚠️ Google authentication needed — set "
                "'Service Account Key Path' below, or run "
                "`gcloud auth application-default login` in a terminal "
                "and restart ComfyUI."
            ),
        }


def _detect_project_id() -> Optional[str]:
    """Detect the GCP project ID. Tries the GCE metadata server first (works
    on Compute Engine / Cloud Run without any creds setup), then falls back
    to Application Default Credentials. Result is cached for the process."""
    global _cached_project_id
    if _cached_project_id is not _UNSET:
        return _cached_project_id  # type: ignore[return-value]

    try:
        import urllib.request
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
        )
        with urllib.request.urlopen(req, timeout=1) as r:
            project = r.read().decode().strip()
            if project:
                _cached_project_id = project
                logger.info(f"VertexAI: detected GCP project from metadata server: {project}")
                return project
    except Exception:
        pass

    try:
        import google.auth
        _, project = google.auth.default()
        if project:
            _cached_project_id = project
            logger.info(f"VertexAI: detected GCP project from ADC: {project}")
            return project
    except Exception:
        pass

    _cached_project_id = None
    return None


_RESERVED_LABEL_KEYS = ("app", "user")


def _merge_reserved_labels(stored_json: Optional[str]) -> str:
    """Always inject the reserved labels (app, user) into the extra_labels
    JSON so the Settings panel reflects the *current* OAuth user. Any stored
    extras (e.g. env=prod) are preserved and kept alongside."""
    try:
        parsed = json.loads(stored_json or "{}")
        if not isinstance(parsed, dict):
            parsed = {}
    except Exception:
        parsed = {}

    parsed["app"] = "comfyui"
    try:
        from .oauth_user import get_oauth_email
        email = get_oauth_email()
        if email:
            parsed["user"] = email
    except Exception:
        pass

    return json.dumps(parsed)


def get_settings() -> dict:
    stored = _read_stored()
    merged = {**_DEFAULTS, **stored}

    if not merged.get("gcp_project"):
        detected = _detect_project_id()
        if detected:
            merged["gcp_project"] = detected

    # Re-inject reserved labels on every read so the displayed user stays
    # in sync with whoever is currently authenticated.
    merged["extra_labels"] = _merge_reserved_labels(merged.get("extra_labels"))

    return merged


def _strip_reserved_labels(extra_labels_json: str) -> str:
    """Remove reserved keys from an incoming extra_labels JSON before persisting
    so we never bake a stale email into the on-disk settings file."""
    try:
        parsed = json.loads(extra_labels_json or "{}")
        if not isinstance(parsed, dict):
            return "{}"
        for key in _RESERVED_LABEL_KEYS:
            parsed.pop(key, None)
        return json.dumps(parsed)
    except Exception:
        return "{}"


def register(prompt_server) -> None:
    @prompt_server.routes.get("/vertexai/settings")
    async def get_handler(request: web.Request) -> web.Response:
        # Capture the OAuth email from this request as well, so the labels
        # default can include `user:` even if /vertexai/whoami hasn't fired yet.
        try:
            from .oauth_user import capture_email_from_request
            capture_email_from_request(request)
        except Exception:
            pass
        return web.json_response({**get_settings(), "auth_status": get_auth_status()})

    @prompt_server.routes.post("/vertexai/settings")
    async def post_handler(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        # Strip reserved label keys so the on-disk file never contains a
        # stale OAuth email; the reserved labels are re-injected on read.
        if "extra_labels" in data and isinstance(data["extra_labels"], str):
            data["extra_labels"] = _strip_reserved_labels(data["extra_labels"])
        stored = _read_stored()
        merged = {**_DEFAULTS, **stored, **data}
        _SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info(f"VertexAI settings saved: {list(data.keys())}")
        # If the SA key path changed, propagate it to the process env so any
        # node executed after this point picks it up. Cached creds inside the
        # google SDK and inside common._cached_email still require a restart.
        if "sa_key_path" in data:
            _apply_sa_key_env()
        return web.json_response({**get_settings(), "auth_status": get_auth_status()})


# Apply any stored SA key path to the process environment at import time so
# every node execution sees GOOGLE_APPLICATION_CREDENTIALS from the first call.
_apply_sa_key_env()
