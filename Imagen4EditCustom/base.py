import io
import json
import logging
import os

import numpy as np
import torch
from PIL import Image as PIL_Image

from google import genai
from google.genai.types import (
    EditImageConfig,
    Image as GenaiImage,
    MaskReferenceConfig,
    MaskReferenceImage,
    RawReferenceImage,
)

from ..common import build_labels as _build_labels, default_labels_json as _default_labels_json

logger = logging.getLogger(__name__)

DEFAULT_EDIT_MODEL = "imagen-4.0-capability-001"
SAFETY_FILTER_LEVELS = ["BLOCK_LOW_AND_ABOVE", "BLOCK_MEDIUM_AND_ABOVE", "BLOCK_ONLY_HIGH", "BLOCK_NONE"]
PERSON_GENERATION_MODES = ["DONT_ALLOW", "ALLOW_ADULT", "ALLOW_ALL"]


class _Imagen4EditBase:
    CATEGORY = "VertexAI/Imagen4"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "execute"

    # ------------------------------------------------------------------ #
    # Client                                                               #
    # ------------------------------------------------------------------ #

    def _get_client(self, gcp_project: str, gcp_location: str) -> genai.Client:
        return genai.Client(vertexai=True, project=gcp_project, location=gcp_location)

    # ------------------------------------------------------------------ #
    # Labels                                                               #
    # ------------------------------------------------------------------ #

    def _parse_labels(self, labels_json: str) -> dict:
        return _build_labels(labels_json)

    def _log_labels(self, labels: dict, model: str, gcp_project: str, gcp_location: str, event: str):
        logger.info(json.dumps({
            "event": event,
            "model": model,
            "gcp_project": gcp_project,
            "gcp_location": gcp_location,
            "labels": labels,
        }))

    # ------------------------------------------------------------------ #
    # Image conversion                                                     #
    # ------------------------------------------------------------------ #

    def _tensor_to_pil(self, tensor: torch.Tensor) -> PIL_Image.Image:
        if tensor.ndim == 4:
            tensor = tensor.squeeze(0)
        return PIL_Image.fromarray((tensor.numpy().clip(0, 1) * 255).astype(np.uint8)).convert("RGB")

    def _mask_to_pil(self, mask: torch.Tensor) -> PIL_Image.Image:
        if mask.ndim == 4:
            mask = mask.squeeze(0)
        if mask.ndim == 3:
            mask = mask.squeeze(0)
        return PIL_Image.fromarray((mask.numpy().clip(0, 1) * 255).astype(np.uint8)).convert("L")

    def _pil_to_genai(self, pil: PIL_Image.Image) -> GenaiImage:
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        return GenaiImage(image_bytes=buf.getvalue())

    def _pil_to_tensor(self, pil: PIL_Image.Image) -> torch.Tensor:
        if pil.mode != "RGB":
            pil = pil.convert("RGB")
        return torch.from_numpy(np.array(pil).astype(np.float32) / 255.0).unsqueeze(0)

    def _pil_to_mask_tensor(self, pil: PIL_Image.Image) -> torch.Tensor:
        if pil.mode != "L":
            pil = pil.convert("L")
        return torch.from_numpy(np.array(pil).astype(np.float32) / 255.0).unsqueeze(0)

    # ------------------------------------------------------------------ #
    # API call                                                             #
    # ------------------------------------------------------------------ #

    def _call_edit(
        self,
        client: genai.Client,
        model_name: str,
        prompt: str,
        refs: list,
        config: EditImageConfig,
    ) -> torch.Tensor:
        logger.info(f"Calling edit_image with model={model_name}, prompt={prompt[:80]!r}")
        response = client.models.edit_image(
            model=model_name,
            prompt=prompt,
            reference_images=refs,
            config=config,
        )
        if not response.generated_images:
            raise RuntimeError("API returned no edited images.")
        tensors = [
            self._pil_to_tensor(PIL_Image.open(io.BytesIO(g.image.image_bytes)))
            for g in response.generated_images
        ]
        return torch.cat(tensors, dim=0)

    # ------------------------------------------------------------------ #
    # Mask reference helpers                                               #
    # ------------------------------------------------------------------ #

    def _make_manual_mask_ref(
        self, mask_tensor: torch.Tensor, mask_dilation: float, ref_id: int = 1
    ) -> MaskReferenceImage:
        return MaskReferenceImage(
            reference_id=ref_id,
            reference_image=self._pil_to_genai(self._mask_to_pil(mask_tensor)),
            config=MaskReferenceConfig(
                mask_mode="MASK_MODE_USER_PROVIDED",
                mask_dilation=mask_dilation,
            ),
        )

    def _make_auto_mask_ref(
        self, mask_mode: str, mask_dilation: float, ref_id: int = 1
    ) -> MaskReferenceImage:
        return MaskReferenceImage(
            reference_id=ref_id,
            reference_image=None,
            config=MaskReferenceConfig(mask_mode=mask_mode, mask_dilation=mask_dilation),
        )

    def _make_semantic_mask_ref(
        self, semantic_classes_csv: str, mask_dilation: float, ref_id: int = 1
    ) -> MaskReferenceImage:
        try:
            classes = [int(s.strip()) for s in semantic_classes_csv.split(",") if s.strip()]
        except ValueError as e:
            raise ValueError(f"semantic_classes_csv must be comma-separated integers: {e}") from e
        if not classes:
            raise ValueError("semantic_classes_csv must contain at least one class ID.")
        return MaskReferenceImage(
            reference_id=ref_id,
            reference_image=None,
            config=MaskReferenceConfig(
                mask_mode="MASK_MODE_SEMANTIC",
                segmentation_classes=classes,
                mask_dilation=mask_dilation,
            ),
        )

    # ------------------------------------------------------------------ #
    # Shared INPUT_TYPES helpers                                           #
    # ------------------------------------------------------------------ #

    @classmethod
    def _gcp_inputs(cls) -> dict:
        return {
            "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "your-gcp-project")}),
            "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
            "model_name": ("STRING", {"default": DEFAULT_EDIT_MODEL}),
        }

    @classmethod
    def _common_optional(cls) -> dict:
        return {
            "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
            "number_of_images": ("INT", {"default": 1, "min": 1, "max": 4}),
            "safety_filter_level": (SAFETY_FILTER_LEVELS, {"default": "BLOCK_MEDIUM_AND_ABOVE"}),
            "person_generation": (PERSON_GENERATION_MODES, {"default": "DONT_ALLOW"}),
            "labels_json": ("STRING", {
                "multiline": False,
                "default": _default_labels_json(),
                "tooltip": 'JSON labels for Cloud Logging / BigQuery tracking. Add extra keys to merge with defaults.',
            }),
        }
