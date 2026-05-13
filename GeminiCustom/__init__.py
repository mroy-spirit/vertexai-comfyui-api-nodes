import logging

logger = logging.getLogger(__name__)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

try:
    from .gemini_vertex import NODE_CLASS_MAPPINGS as _IMG_CLS, NODE_DISPLAY_NAME_MAPPINGS as _IMG_NAMES
    NODE_CLASS_MAPPINGS.update(_IMG_CLS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_IMG_NAMES)
except ImportError as e:
    logger.warning(f"GeminiVertex nodes disabled (missing dep): {e}")

try:
    from .gemini_text import NODE_CLASS_MAPPINGS as _TXT_CLS, NODE_DISPLAY_NAME_MAPPINGS as _TXT_NAMES
    NODE_CLASS_MAPPINGS.update(_TXT_CLS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_TXT_NAMES)
except ImportError as e:
    logger.warning(f"GeminiText node disabled (missing dep — pip install google-genai): {e}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
