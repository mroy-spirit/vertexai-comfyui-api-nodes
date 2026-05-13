import json
import logging
from pathlib import Path

from aiohttp import web

logger = logging.getLogger(__name__)

_SETTINGS_FILE = Path(__file__).parent / "vertexai-settings.json"

_DEFAULTS: dict = {
    "gcp_project": "",
    "gcp_location": "us-central1",
    "storage_uri": "gs://your-bucket/output/",
    "extra_labels": "{}",
}


def get_settings() -> dict:
    try:
        stored = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**_DEFAULTS, **stored}
    except Exception:
        return dict(_DEFAULTS)


def register(prompt_server) -> None:
    @prompt_server.routes.get("/vertexai/settings")
    async def get_handler(request: web.Request) -> web.Response:
        return web.json_response(get_settings())

    @prompt_server.routes.post("/vertexai/settings")
    async def post_handler(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        merged = {**get_settings(), **data}
        _SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        logger.info(f"VertexAI settings saved: {list(data.keys())}")
        return web.json_response(merged)
