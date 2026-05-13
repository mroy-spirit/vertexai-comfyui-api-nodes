import io
import json
import logging
import os
from typing import Optional

import numpy as np
import torch
from PIL import Image as PIL_Image

from google import genai
from google.genai import types as genai_types

from ..common import build_labels

logger = logging.getLogger(__name__)


class GeminiTextVertexAINode:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "your-gcp-project")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "model": ("STRING", {"default": "gemini-2.0-flash-001"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "temperature": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
                "top_k": ("INT", {"default": 1, "min": 1, "max": 40}),
                "max_output_tokens": ("INT", {"default": 2048, "min": 1, "max": 8192, "step": 64}),
                "stop_sequences": ("STRING", {"multiline": False, "default": "", "tooltip": "Comma-separated stop sequences"}),
                "image": ("IMAGE",),
                "video_urls": ("STRING", {"multiline": True, "default": "", "tooltip": "One GCS video URL per line (gs://...)"}),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("generated_text",)
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(
        self,
        gcp_project: str,
        gcp_location: str,
        model: str,
        prompt: str,
        temperature: float = 0.9,
        top_p: float = 1.0,
        top_k: int = 1,
        max_output_tokens: int = 2048,
        stop_sequences: str = "",
        image: Optional[torch.Tensor] = None,
        video_urls: str = "",
        custom_label_key: str = "",
        custom_label_value: str = "",
    ):
        logger.info(json.dumps({
            "event": "gemini_text_request",
            "model": model,
            "gcp_project": gcp_project,
            "gcp_location": gcp_location,
            "labels": build_labels(custom_label_key, custom_label_value),
        }))

        client = genai.Client(vertexai=True, project=gcp_project, location=gcp_location)

        parts = [genai_types.Part.from_text(text=prompt)]

        if image is not None:
            img_tensor = image[0] if image.ndim == 4 else image
            np_img = (img_tensor.numpy().clip(0, 1) * 255).astype(np.uint8)
            pil_img = PIL_Image.fromarray(np_img).convert("RGB")
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            parts.append(genai_types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png"))

        if video_urls and video_urls.strip():
            for url in video_urls.strip().splitlines():
                url = url.strip()
                if url:
                    parts.append(genai_types.Part.from_uri(file_uri=url, mime_type="video/mp4"))

        stops = [s.strip() for s in stop_sequences.split(",") if s.strip()] if stop_sequences else []
        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_output_tokens=max_output_tokens,
            stop_sequences=stops or None,
        )

        logger.info(f"Sending text request → model={model}")
        response = client.models.generate_content(
            model=model,
            contents=[genai_types.Content(role="user", parts=parts)],
            config=config,
        )

        try:
            text = response.text
        except ValueError as e:
            raise RuntimeError(f"Content blocked or unavailable: {e}") from e

        return (text,)


NODE_CLASS_MAPPINGS = {
    "GeminiTextVertexAINode": GeminiTextVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "GeminiTextVertexAINode": "Gemini Text (Vertex AI)",
}
