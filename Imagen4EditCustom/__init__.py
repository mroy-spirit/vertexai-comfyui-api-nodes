import logging

logger = logging.getLogger(__name__)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

try:
    from .bg_swap import NODE_CLASS_MAPPINGS as _BG, NODE_DISPLAY_NAME_MAPPINGS as _BG_NAMES
    from .inpaint import NODE_CLASS_MAPPINGS as _IP, NODE_DISPLAY_NAME_MAPPINGS as _IP_NAMES
    from .maskfree import NODE_CLASS_MAPPINGS as _MF, NODE_DISPLAY_NAME_MAPPINGS as _MF_NAMES
    from .outpaint import NODE_CLASS_MAPPINGS as _OP, NODE_DISPLAY_NAME_MAPPINGS as _OP_NAMES
    NODE_CLASS_MAPPINGS.update({**_BG, **_IP, **_MF, **_OP})
    NODE_DISPLAY_NAME_MAPPINGS.update({**_BG_NAMES, **_IP_NAMES, **_MF_NAMES, **_OP_NAMES})
except ImportError as e:
    logger.warning(f"Imagen4Edit nodes disabled (missing dep — pip install google-genai): {e}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
