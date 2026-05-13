import json
import logging
import os

import numpy as np
import torch

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel

logger = logging.getLogger(__name__)

_IMAGEN4_MODELS = [
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
]

_ASPECT_RATIOS = ["1:1", "5:4", "3:2", "7:4", "4:3", "16:9", "9:16"]


class Imagen4:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "vertex-ai-model-location")}),
                "model_name": (_IMAGEN4_MODELS,),
                "prompt": ("STRING", {"multiline": True, "default": "A beautiful landscape"}),
            },
            "optional": {
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "number_of_images": ("INT", {"default": 1, "min": 1, "max": 4}),
                "aspect_ratio": (_ASPECT_RATIOS,),
                "sample_image_size": (["1K", "2K"],),
                "guidance_scale": ("FLOAT", {"default": 15.0, "min": 0.0, "max": 30.0, "step": 0.5}),
                "person_generation": (["dont_allow", "allow_none", "allow_adult", "allow_all"],),
                "safety_filter_level": (["block_low_and_above", "block_medium_and_above", "block_only_high", "block_none"],),
                "add_watermark": ("BOOLEAN", {"default": False}),
                "labels_json": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": 'JSON labels for Cloud Logging / BigQuery tracking. Example: {"env": "prod"}',
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

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

    def execute(
        self,
        gcp_project,
        gcp_location,
        model_name,
        prompt,
        negative_prompt="",
        seed=0,
        number_of_images=1,
        aspect_ratio="1:1",
        sample_image_size="1K",
        guidance_scale=15.0,
        person_generation="dont_allow",
        safety_filter_level="block_medium_and_above",
        add_watermark=False,
        labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            logger.info(json.dumps({
                "event": "imagen4_vertex_request",
                "model": model_name,
                "gcp_project": gcp_project,
                "gcp_location": gcp_location,
                "labels": labels,
            }))

        try:
            vertexai.init(project=gcp_project, location=gcp_location)
            model = ImageGenerationModel.from_pretrained(model_name)

            response = model.generate_images(
                prompt=prompt,
                negative_prompt=negative_prompt or None,
                seed=seed,
                number_of_images=number_of_images,
                aspect_ratio=aspect_ratio,
                guidance_scale=guidance_scale,
                person_generation=person_generation,
                safety_filter_level=safety_filter_level,
                add_watermark=add_watermark,
            )

            if not response.images:
                raise RuntimeError("The API did not return any images.")

            tensors = []
            for img in response.images:
                np_image = np.array(img._pil_image).astype(np.float32) / 255.0
                tensors.append(torch.from_numpy(np_image))

            return (torch.stack(tensors, dim=0),)

        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return (torch.zeros((1, 512, 512, 3)),)


NODE_CLASS_MAPPINGS = {
    "Imagen4VertexAINode": Imagen4,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Imagen4VertexAINode": "Imagen4 Image Generator (Vertex AI)",
}
