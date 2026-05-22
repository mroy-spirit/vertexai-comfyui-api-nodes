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

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

_SUBPACKAGES = (
    "Veo3Custom", "GeminiCustom",
    "VideoPreviewCustom", "UtilsCustom",
)

for _pkg_name in _SUBPACKAGES:
    try:
        _mod = __import__(
            f"{__name__}.{_pkg_name}",
            fromlist=["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"],
        )
        NODE_CLASS_MAPPINGS.update(getattr(_mod, "NODE_CLASS_MAPPINGS", {}))
        NODE_DISPLAY_NAME_MAPPINGS.update(getattr(_mod, "NODE_DISPLAY_NAME_MAPPINGS", {}))
    except Exception as _e:
        _logging.getLogger(__name__).warning(
            f"Subpackage {_pkg_name} failed to load and its nodes will be unavailable: {_e}"
        )

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
