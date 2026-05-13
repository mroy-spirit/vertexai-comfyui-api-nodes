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


def _compute_default_labels_json() -> str:
    """JSON-encoded labels that build_labels() will always apply: app + user."""
    labels = {"app": "comfyui"}
    try:
        from .oauth_user import get_oauth_email
        email = get_oauth_email()
        if email:
            labels["user"] = email
    except Exception:
        pass
    return json.dumps(labels)


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

    if merged.get("extra_labels") in (None, "", "{}"):
        merged["extra_labels"] = _compute_default_labels_json()

    return merged


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
        try:
            stored = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            stored = {}
        merged = {**_DEFAULTS, **stored, **data}
        _SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info(f"VertexAI settings saved: {list(data.keys())}")
        return web.json_response(get_settings())
