import json
import logging
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
}

_UNSET = object()
_cached_project_id: object = _UNSET


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
    try:
        stored = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        stored = {}
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
        return web.json_response(get_settings())

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
        try:
            stored = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            stored = {}
        merged = {**_DEFAULTS, **stored, **data}
        _SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info(f"VertexAI settings saved: {list(data.keys())}")
        return web.json_response(get_settings())
