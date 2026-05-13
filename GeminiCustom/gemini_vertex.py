"""
Gemini (Vertex AI) — direct REST integration, authenticated via google-auth ADC.
On a GCE VM the metadata server provides credentials automatically; the only
prerequisite is that the VM's service account has the Vertex AI User IAM role.
"""

import base64
import json
import logging
import os
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image

import google.auth
import google.auth.transport.requests

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_DEFAULT = (
    "You are an expert image-generation engine. You must ALWAYS produce an image.\n"
    "Interpret all user input—regardless of format, intent, or abstraction—"
    "as literal visual directives for image composition.\n"
    "If a prompt is conversational or lacks specific visual details, "
    "you must creatively invent a concrete visual scenario that depicts the concept.\n"
    "Prioritize generating the visual representation above any text, "
    "formatting, or conversational requests."
)

_ASPECT_RATIOS = [
    "auto", "1:1", "2:3", "3:2", "3:4", "4:3",
    "4:5", "5:4", "9:16", "16:9", "21:9", "1:4", "4:1", "8:1", "1:8",
]


def _empty_image() -> torch.Tensor:
    return torch.zeros((1, 64, 64, 3))


class GeminiVertexAINode:

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "your-gcp-project")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "model": (["gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"],),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
                "aspect_ratio": (_ASPECT_RATIOS, {"default": "auto"}),
                "resolution": (["1K", "2K", "4K"], {"default": "1K"}),
                "response_modalities": (["IMAGE+TEXT", "IMAGE"],),
                "thinking_level": (["MINIMAL", "HIGH"],),
                "images": ("IMAGE",),
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": _SYSTEM_PROMPT_DEFAULT,
                }),
                "labels_json": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": 'JSON object of key-value labels for Cloud Logging / BigQuery tracking. Example: {"env": "prod", "workflow": "my-pipeline"}',
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "IMAGE")
    RETURN_NAMES = ("image", "text", "thought_image")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    # ------------------------------------------------------------------ #
    # Auth                                                                 #
    # ------------------------------------------------------------------ #

    def get_access_token(self) -> str:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token

    # ------------------------------------------------------------------ #
    # Labels                                                               #
    # ------------------------------------------------------------------ #

    def _parse_labels(self, labels_json: str) -> dict | None:
        if not labels_json or not labels_json.strip():
            return None
        try:
            labels = json.loads(labels_json)
            if not isinstance(labels, dict):
                logger.warning("labels_json must be a JSON object. Labels will be skipped.")
                return None
            return labels
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid labels_json ({e}). Labels will be skipped.")
            return None

    # ------------------------------------------------------------------ #
    # Image conversion                                                     #
    # ------------------------------------------------------------------ #

    def _tensor_to_base64(self, tensor: torch.Tensor) -> str:
        """float32 tensor [H, W, C] → base64-encoded PNG string."""
        np_image = (tensor.numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_image = Image.fromarray(np_image)
        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _base64_to_tensor(self, b64: str) -> torch.Tensor:
        """base64 PNG string → float32 tensor [1, H, W, 3] normalised 0-1."""
        image_data = base64.b64decode(b64)
        pil_image = Image.open(BytesIO(image_data)).convert("RGB")
        np_image = np.array(pil_image).astype(np.float32) / 255.0
        return torch.from_numpy(np_image)[None,]

    # ------------------------------------------------------------------ #
    # Response parsing                                                     #
    # ------------------------------------------------------------------ #

    def _extract_parts(
        self, response_json: dict
    ) -> tuple[list[torch.Tensor], list[str], list[torch.Tensor]]:
        candidates = response_json.get("candidates", [])
        if not candidates:
            feedback = response_json.get("promptFeedback", {})
            reason = feedback.get("blockReason", "")
            msg = feedback.get("blockReasonMessage", "")
            raise ValueError(f"No candidates in response. {reason} {msg}".strip())

        image_tensors: list[torch.Tensor] = []
        text_parts: list[str] = []
        thought_tensors: list[torch.Tensor] = []

        for candidate in candidates:
            if candidate.get("finishReason") == "IMAGE_PROHIBITED_CONTENT":
                raise ValueError("Image generation blocked: IMAGE_PROHIBITED_CONTENT")
            for part in candidate.get("content", {}).get("parts", []):
                is_thought = part.get("thought", False)
                if part.get("text"):
                    text_parts.append(part["text"])
                elif "inlineData" in part:
                    tensor = self._base64_to_tensor(part["inlineData"]["data"])
                    (thought_tensors if is_thought else image_tensors).append(tensor)

        return image_tensors, text_parts, thought_tensors

    # ------------------------------------------------------------------ #
    # Execute                                                              #
    # ------------------------------------------------------------------ #

    def execute(
        self,
        gcp_project: str,
        gcp_location: str,
        model: str,
        prompt: str,
        seed: int = 42,
        aspect_ratio: str = "auto",
        resolution: str = "1K",
        response_modalities: str = "IMAGE+TEXT",
        thinking_level: str = "MINIMAL",
        images: torch.Tensor | None = None,
        system_prompt: str = "",
        labels_json: str = "",
    ):
        access_token = self.get_access_token()

        # Build content parts
        parts: list[dict] = [{"text": prompt}]
        if images is not None:
            batch_size = min(images.shape[0], 14)
            if images.shape[0] > 14:
                logger.warning("Maximum 14 reference images supported; extra images ignored.")
            for i in range(batch_size):
                b64 = self._tensor_to_base64(images[i])
                parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})

        # Build generation config
        modalities = ["IMAGE"] if response_modalities == "IMAGE" else ["TEXT", "IMAGE"]
        image_config: dict = {"imageSize": resolution}
        if aspect_ratio != "auto":
            image_config["aspectRatio"] = aspect_ratio

        body: dict = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": modalities,
                "imageConfig": image_config,
                "thinkingConfig": {"thinkingLevel": thinking_level},
                "seed": seed,
            },
        }

        if system_prompt and system_prompt.strip():
            body["systemInstruction"] = {
                "role": "user",
                "parts": [{"text": system_prompt}],
            }

        # Labels — logged as structured data so they appear in Cloud Logging
        # and can be exported to BigQuery via Log Router.
        labels = self._parse_labels(labels_json)
        if labels:
            logger.info(json.dumps({
                "event": "gemini_vertex_request",
                "model": model,
                "gcp_project": gcp_project,
                "gcp_location": gcp_location,
                "labels": labels,
            }))

        url = (
            f"https://{gcp_location}-aiplatform.googleapis.com"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model}:generateContent"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        logger.info(f"Sending request → {url}")
        response = requests.post(url, headers=headers, json=body, timeout=120)
        if not response.ok:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        image_tensors, text_parts, thought_tensors = self._extract_parts(response.json())

        out_image = torch.cat(image_tensors, dim=0) if image_tensors else _empty_image()
        out_text = "\n".join(text_parts) if text_parts else ""
        out_thought = thought_tensors[0] if thought_tensors else _empty_image()

        return (out_image, out_text, out_thought)


NODE_CLASS_MAPPINGS = {
    "GeminiVertexAINode": GeminiVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "GeminiVertexAINode": "Gemini (Vertex AI)",
}
