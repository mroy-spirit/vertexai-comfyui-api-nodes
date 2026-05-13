import logging as _logging

def _register_oauth_routes():
    try:
        import server
        from .oauth_user import register
        register(server.PromptServer.instance)
    except Exception as _e:
        _logging.getLogger(__name__).warning(f"Could not register /vertexai/whoami route: {_e}")

def _register_settings_routes():
    try:
        import server
        from .vertexai_settings import register
        register(server.PromptServer.instance)
    except Exception as _e:
        _logging.getLogger(__name__).warning(f"Could not register /vertexai/settings routes: {_e}")

_register_oauth_routes()
_register_settings_routes()

from .Imagen4Custom import NODE_CLASS_MAPPINGS as _IMAGEN4_CLS, NODE_DISPLAY_NAME_MAPPINGS as _IMAGEN4_NAMES
from .Veo3Custom import NODE_CLASS_MAPPINGS as _VEO3_CLS, NODE_DISPLAY_NAME_MAPPINGS as _VEO3_NAMES
from .GeminiCustom import NODE_CLASS_MAPPINGS as _GEMINI_CLS, NODE_DISPLAY_NAME_MAPPINGS as _GEMINI_NAMES
from .VideoPreviewCustom import NODE_CLASS_MAPPINGS as _PREVIEW_CLS, NODE_DISPLAY_NAME_MAPPINGS as _PREVIEW_NAMES
from .Imagen4EditCustom import NODE_CLASS_MAPPINGS as _EDIT_CLS, NODE_DISPLAY_NAME_MAPPINGS as _EDIT_NAMES
from .UtilsCustom import NODE_CLASS_MAPPINGS as _UTILS_CLS, NODE_DISPLAY_NAME_MAPPINGS as _UTILS_NAMES

NODE_CLASS_MAPPINGS = {
    **_IMAGEN4_CLS, **_VEO3_CLS, **_GEMINI_CLS,
    **_PREVIEW_CLS, **_EDIT_CLS, **_UTILS_CLS,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    **_IMAGEN4_NAMES, **_VEO3_NAMES, **_GEMINI_NAMES,
    **_PREVIEW_NAMES, **_EDIT_NAMES, **_UTILS_NAMES,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
