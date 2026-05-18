"""
Veo (Vertex AI) — direct REST integration, authenticated via google-auth ADC.
On a GCE VM the metadata server provides credentials automatically; the only
prerequisite is that the VM's service account has the Vertex AI User IAM role.
"""

import base64
import json
import logging
import os
import time
from io import BytesIO

import numpy as np
import requests
import torch
from PIL import Image

import google.auth
import google.auth.transport.requests

import folder_paths

from ..common import build_labels

logger = logging.getLogger(__name__)

_VEO3_MODELS = [
    "veo-3.0-generate-001",
    "veo-3.0-fast-generate-001",
    "veo-3.1-generate-001",
    "veo-3.1-fast-generate-001",
    "veo-3.1-lite-generate-001",
]

_VEO31_MODELS = [
    "veo-3.1-generate-001",
    "veo-3.1-fast-generate-001",
    "veo-3.1-lite-generate-001",
]

_VEO2_MODELS = [
    "veo-2.0-generate-001",
    "veo-2.0-generate-exp",
    "veo-2.0-generate-preview",
]


class _VeoBase:
    """Shared auth, image conversion, label logging, polling and download helpers."""

    def get_access_token(self) -> str:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token

    @staticmethod
    def _api_host(gcp_location: str) -> str:
        if gcp_location == "global":
            return "https://aiplatform.googleapis.com"
        return f"https://{gcp_location}-aiplatform.googleapis.com"

    def _tensor_to_base64(self, tensor: torch.Tensor) -> str:
        """float32 tensor [H, W, C] → base64-encoded PNG string."""
        np_image = (tensor.numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_image = Image.fromarray(np_image)
        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _mask_to_base64(self, mask: torch.Tensor) -> str:
        """ComfyUI MASK tensor [B, H, W] float[0,1] → base64-encoded 8-bit PNG (white = region to fill)."""
        arr = mask[0] if mask.dim() == 3 else mask
        np_mask = (arr.numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_mask = Image.fromarray(np_mask, mode="L")
        buf = BytesIO()
        pil_mask.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def _log_labels(self, labels: dict, model_id: str, gcp_project: str, gcp_location: str):
        logger.info(json.dumps({
            "event": "veo_vertex_request",
            "model": model_id,
            "gcp_project": gcp_project,
            "gcp_location": gcp_location,
            "labels": labels,
        }))

    def download_gcs_file(self, gcs_uri: str, local_path: str, access_token: str):
        """Download a GCS object via the storage JSON API (no gcloud CLI needed)."""
        path = gcs_uri[5:]  # strip "gs://"
        bucket, obj = path.split("/", 1)
        url = f"https://storage.googleapis.com/{bucket}/{obj}"
        logger.info(f"Downloading {gcs_uri} → {local_path}")
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info("Download complete.")

    def poll_operation(
        self, operation_id: str, gcp_project: str, gcp_location: str, model_id: str, access_token: str
    ) -> str:
        """Poll the long-running operation until done. Returns the GCS URI or raises."""
        url = (
            f"{self._api_host(gcp_location)}"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model_id}:fetchPredictOperation"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"operationName": operation_id}
        deadline = time.time() + 900  # 15 min

        while time.time() < deadline:
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                status = resp.json()
            except requests.exceptions.HTTPError as e:
                raise Exception(f"HTTP error while polling: {e}\n{e.response.text}")
            except Exception as e:
                raise Exception(f"Unexpected error during polling: {e}")

            if not status.get("done", False):
                logger.info("Operation in progress, retrying in 15 s…")
                time.sleep(15)
                continue

            if "error" in status:
                err = status["error"]
                raise Exception(
                    f"Operation failed: {err.get('message', 'Unknown error')} (code {err.get('code')})"
                )

            response_data = status.get("response", {})

            rai_count = response_data.get("raiMediaFilteredCount", 0)
            if rai_count:
                reasons = response_data.get("raiMediaFilteredReasons", [])
                suffix = f": {reasons[0]}" if reasons else ""
                raise Exception(
                    f"Content blocked by Responsible AI filters{suffix} "
                    f"({rai_count} video{'s' if rai_count != 1 else ''} filtered)."
                )

            for video in response_data.get("videos", []):
                if video.get("gcsUri", "").startswith("gs://"):
                    return video["gcsUri"]

            raise Exception(f"Operation done but no GCS URI in response: {response_data}")

        raise Exception("Polling timed out after 15 minutes.")

    def _submit_and_collect(
        self,
        instance: dict,
        parameters: dict,
        gcp_project: str,
        gcp_location: str,
        model_id: str,
        access_token: str,
    ) -> tuple:
        """Submit a predictLongRunning job, poll to completion, download the result.
        Returns (local_video_path, gcs_uri). Payload bodies are not dumped to logs
        because most modes carry base64 image/mask blobs."""
        url = (
            f"{self._api_host(gcp_location)}"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model_id}:predictLongRunning"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"instances": [instance], "parameters": parameters}
        logger.info(
            f"Sending request → {url} (instance keys: {sorted(instance.keys())}, "
            f"parameter keys: {sorted(parameters.keys())})"
        )

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if not resp.ok:
            raise Exception(f"HTTP {resp.status_code} on submission: {resp.text}")

        operation_id = resp.json().get("name")
        if not operation_id:
            raise Exception("No operation ID in submission response.")
        logger.info(f"Job started. Operation ID: {operation_id}")

        gcs_uri = self.poll_operation(operation_id, gcp_project, gcp_location, model_id, access_token)

        output_dir = folder_paths.get_output_directory()
        local_path = os.path.join(output_dir, os.path.basename(gcs_uri))
        self.download_gcs_file(gcs_uri, local_path, access_token)
        return (local_path, gcs_uri)


class Veo3VertexAINode(_VeoBase):

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "prompt": ("STRING", {"multiline": True, "default": "A cinematic, aerial shot of a futuristic city with flying cars at sunset."}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket/video-output/"}),
            },
            "optional": {
                "model_id": (_VEO3_MODELS, {"default": "veo-3.0-generate-001"}),
                "aspect_ratio": (["16:9", "9:16", "1:1", "4:5"],),
                "duration_seconds": ("INT", {"default": 8, "min": 4, "max": 8, "step": 2}),
                "resolution": (["720p", "1080p", "4k"],),
                "generate_audio": ("BOOLEAN", {"default": True}),
                "person_generation": (["allow_all", "dont_allow"],),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "image": ("IMAGE",),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("local_video_path", "gcs_uri")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(
        self,
        gcp_project, gcp_location, prompt, storage_uri,
        model_id="veo-3.0-generate-001",
        aspect_ratio="16:9",
        duration_seconds=8,
        resolution="720p",
        generate_audio=True,
        person_generation="allow_all",
        seed=0,
        negative_prompt="",
        enhance_prompt=True,
        image=None,
        custom_label_key="",
        custom_label_value="",
    ):
        if resolution == "4k" and model_id in ("veo-3.0-generate-001", "veo-3.0-fast-generate-001"):
            raise ValueError("4K resolution is not supported by Veo 3.0 models.")

        access_token = self.get_access_token()

        self._log_labels(build_labels(custom_label_key, custom_label_value), model_id, gcp_project, gcp_location)

        instances = [{"prompt": prompt}]
        if image is not None:
            instances[0]["image"] = {
                "bytesBase64Encoded": self._tensor_to_base64(image[0]),
                "mimeType": "image/png",
            }

        parameters = {
            "storageUri": storage_uri,
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": duration_seconds,
            "personGeneration": person_generation,
            "includeRaiReason": True,
            "generateAudio": generate_audio,
            "enhancePrompt": enhance_prompt,
            "resolution": resolution,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        url = (
            f"{self._api_host(gcp_location)}"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model_id}:predictLongRunning"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"instances": instances, "parameters": parameters}
        logger.info(f"Sending request → {url}\n{json.dumps(payload, indent=2)}")

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if not resp.ok:
            raise Exception(f"HTTP {resp.status_code} on submission: {resp.text}")

        operation_id = resp.json().get("name")
        if not operation_id:
            raise Exception("No operation ID in submission response.")
        logger.info(f"Job started. Operation ID: {operation_id}")

        gcs_uri = self.poll_operation(operation_id, gcp_project, gcp_location, model_id, access_token)

        output_dir = folder_paths.get_output_directory()
        local_path = os.path.join(output_dir, os.path.basename(gcs_uri))
        self.download_gcs_file(gcs_uri, local_path, access_token)
        return (local_path, gcs_uri)


class Veo3FirstLastFrameVertexAINode(_VeoBase):

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket/video-output/"}),
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
            },
            "optional": {
                "model_id": (_VEO31_MODELS, {"default": "veo-3.1-generate-001"}),
                "aspect_ratio": (["16:9", "9:16"],),
                "duration_seconds": ("INT", {"default": 8, "min": 4, "max": 8, "step": 2}),
                "resolution": (["720p", "1080p", "4k"],),
                "generate_audio": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("local_video_path", "gcs_uri")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(
        self,
        gcp_project, gcp_location, prompt, storage_uri, first_frame, last_frame,
        model_id="veo-3.1-generate-001",
        aspect_ratio="16:9",
        duration_seconds=8,
        resolution="720p",
        generate_audio=True,
        seed=0,
        negative_prompt="",
        custom_label_key="",
        custom_label_value="",
    ):
        if resolution == "4k" and "lite" in model_id:
            raise ValueError("4K resolution is not supported by veo-3.1-lite.")

        access_token = self.get_access_token()

        self._log_labels(build_labels(custom_label_key, custom_label_value), model_id, gcp_project, gcp_location)

        instance = {
            "prompt": prompt,
            "image": {
                "bytesBase64Encoded": self._tensor_to_base64(first_frame[0]),
                "mimeType": "image/png",
            },
            "lastFrame": {
                "bytesBase64Encoded": self._tensor_to_base64(last_frame[0]),
                "mimeType": "image/png",
            },
        }

        parameters = {
            "storageUri": storage_uri,
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": duration_seconds,
            "includeRaiReason": True,
            "generateAudio": generate_audio,
            "enhancePrompt": True,
            "resolution": resolution,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        url = (
            f"{self._api_host(gcp_location)}"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model_id}:predictLongRunning"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"instances": [instance], "parameters": parameters}
        logger.info(f"Sending request → {url}")

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if not resp.ok:
            raise Exception(f"HTTP {resp.status_code} on submission: {resp.text}")

        operation_id = resp.json().get("name")
        if not operation_id:
            raise Exception("No operation ID in submission response.")
        logger.info(f"Job started. Operation ID: {operation_id}")

        gcs_uri = self.poll_operation(operation_id, gcp_project, gcp_location, model_id, access_token)

        output_dir = folder_paths.get_output_directory()
        local_path = os.path.join(output_dir, os.path.basename(gcs_uri))
        self.download_gcs_file(gcs_uri, local_path, access_token)
        return (local_path, gcs_uri)


class Veo3ExtendVertexAINode(_VeoBase):
    """Extend an existing Veo-generated MP4 by ~7 s. Veo 3.1 only.
    Input video MUST be a gs:// URI; the API does not accept base64 video."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket/video-output/"}),
                "input_video_gcs_uri": ("STRING", {"default": "", "tooltip": "gs:// URI of a Veo-generated MP4 to extend"}),
            },
            "optional": {
                "model_id": (_VEO31_MODELS, {"default": "veo-3.1-generate-001"}),
                "aspect_ratio": (["16:9", "9:16"],),
                "resolution": (["720p", "1080p", "4k"],),
                "generate_audio": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("local_video_path", "gcs_uri")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(
        self,
        gcp_project, gcp_location, prompt, storage_uri, input_video_gcs_uri,
        model_id="veo-3.1-generate-001",
        aspect_ratio="16:9",
        resolution="720p",
        generate_audio=True,
        seed=0,
        negative_prompt="",
        enhance_prompt=True,
        custom_label_key="",
        custom_label_value="",
    ):
        if not input_video_gcs_uri or not input_video_gcs_uri.startswith("gs://"):
            raise ValueError("input_video_gcs_uri must be a gs:// URI (the Veo API does not accept base64 video).")
        if resolution == "4k" and "lite" in model_id:
            raise ValueError("4K resolution is not supported by veo-3.1-lite.")

        access_token = self.get_access_token()
        self._log_labels(build_labels(custom_label_key, custom_label_value), model_id, gcp_project, gcp_location)

        instance = {
            "prompt": prompt,
            "video": {"gcsUri": input_video_gcs_uri, "mimeType": "video/mp4"},
        }
        parameters = {
            "storageUri": storage_uri,
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "includeRaiReason": True,
            "generateAudio": generate_audio,
            "enhancePrompt": enhance_prompt,
            "resolution": resolution,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        return self._submit_and_collect(instance, parameters, gcp_project, gcp_location, model_id, access_token)


class Veo3ReferenceSubjectVertexAINode(_VeoBase):
    """Generate a video conditioned on 1-3 subject reference images. Veo 3.1.
    Duration is locked to 8 s by the Vertex API when referenceImages is set."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket/video-output/"}),
                "reference_image_1": ("IMAGE",),
            },
            "optional": {
                "reference_image_2": ("IMAGE",),
                "reference_image_3": ("IMAGE",),
                "model_id": (_VEO31_MODELS, {"default": "veo-3.1-generate-001"}),
                "aspect_ratio": (["16:9", "9:16"],),
                "resolution": (["720p", "1080p", "4k"],),
                "generate_audio": ("BOOLEAN", {"default": True}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("local_video_path", "gcs_uri")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(
        self,
        gcp_project, gcp_location, prompt, storage_uri, reference_image_1,
        reference_image_2=None,
        reference_image_3=None,
        model_id="veo-3.1-generate-001",
        aspect_ratio="16:9",
        resolution="720p",
        generate_audio=True,
        seed=0,
        negative_prompt="",
        enhance_prompt=True,
        custom_label_key="",
        custom_label_value="",
    ):
        if resolution == "4k" and "lite" in model_id:
            raise ValueError("4K resolution is not supported by veo-3.1-lite.")

        access_token = self.get_access_token()
        self._log_labels(build_labels(custom_label_key, custom_label_value), model_id, gcp_project, gcp_location)

        reference_images = []
        for img in (reference_image_1, reference_image_2, reference_image_3):
            if img is None:
                continue
            reference_images.append({
                "image": {
                    "bytesBase64Encoded": self._tensor_to_base64(img[0]),
                    "mimeType": "image/png",
                },
                "referenceType": "asset",
            })

        instance = {"prompt": prompt, "referenceImages": reference_images}
        parameters = {
            "storageUri": storage_uri,
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": 8,
            "includeRaiReason": True,
            "generateAudio": generate_audio,
            "enhancePrompt": enhance_prompt,
            "resolution": resolution,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        return self._submit_and_collect(instance, parameters, gcp_project, gcp_location, model_id, access_token)


class VeoReferenceStyleVertexAINode(_VeoBase):
    """Generate a video in the style of a single reference image. Veo 2 only —
    Veo 3.1 does not support referenceImages.style. Duration locked to 8 s."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket/video-output/"}),
                "style_reference_image": ("IMAGE",),
            },
            "optional": {
                "model_id": (_VEO2_MODELS, {"default": "veo-2.0-generate-001"}),
                "aspect_ratio": (["16:9", "9:16"],),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("local_video_path", "gcs_uri")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(
        self,
        gcp_project, gcp_location, prompt, storage_uri, style_reference_image,
        model_id="veo-2.0-generate-001",
        aspect_ratio="16:9",
        seed=0,
        negative_prompt="",
        enhance_prompt=True,
        custom_label_key="",
        custom_label_value="",
    ):
        access_token = self.get_access_token()
        self._log_labels(build_labels(custom_label_key, custom_label_value), model_id, gcp_project, gcp_location)

        instance = {
            "prompt": prompt,
            "referenceImages": [{
                "image": {
                    "bytesBase64Encoded": self._tensor_to_base64(style_reference_image[0]),
                    "mimeType": "image/png",
                },
                "referenceType": "style",
            }],
        }
        parameters = {
            "storageUri": storage_uri,
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": 8,
            "includeRaiReason": True,
            "enhancePrompt": enhance_prompt,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        return self._submit_and_collect(instance, parameters, gcp_project, gcp_location, model_id, access_token)


class VeoInpaintInsertVertexAINode(_VeoBase):
    """Insert an object into an existing video region. Veo 2 only.
    Video input is gs:// URI; mask is a ComfyUI MASK tensor (white = region to fill)."""

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "us-central1")}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket/video-output/"}),
                "input_video_gcs_uri": ("STRING", {"default": "", "tooltip": "gs:// URI of the MP4 to edit"}),
                "mask": ("MASK",),
            },
            "optional": {
                "model_id": (_VEO2_MODELS, {"default": "veo-2.0-generate-001"}),
                "aspect_ratio": (["16:9", "9:16"],),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0x7FFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "custom_label_key": ("STRING", {"default": "", "tooltip": "Optional label key, e.g. workflow"}),
                "custom_label_value": ("STRING", {"default": "", "tooltip": "Optional label value, e.g. product-shot"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("local_video_path", "gcs_uri")
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    _MASK_MODE = "insert"

    def execute(
        self,
        gcp_project, gcp_location, prompt, storage_uri, input_video_gcs_uri, mask,
        model_id="veo-2.0-generate-001",
        aspect_ratio="16:9",
        seed=0,
        negative_prompt="",
        enhance_prompt=True,
        custom_label_key="",
        custom_label_value="",
    ):
        if not input_video_gcs_uri or not input_video_gcs_uri.startswith("gs://"):
            raise ValueError("input_video_gcs_uri must be a gs:// URI (the Veo API does not accept base64 video).")

        access_token = self.get_access_token()
        self._log_labels(build_labels(custom_label_key, custom_label_value), model_id, gcp_project, gcp_location)

        instance = {
            "prompt": prompt,
            "video": {"gcsUri": input_video_gcs_uri, "mimeType": "video/mp4"},
            "mask": {
                "bytesBase64Encoded": self._mask_to_base64(mask),
                "mimeType": "image/png",
                "maskMode": self._MASK_MODE,
            },
        }
        parameters = {
            "storageUri": storage_uri,
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "includeRaiReason": True,
            "enhancePrompt": enhance_prompt,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        return self._submit_and_collect(instance, parameters, gcp_project, gcp_location, model_id, access_token)


class VeoInpaintRemoveVertexAINode(VeoInpaintInsertVertexAINode):
    """Remove an object from an existing video region. Veo 2 only.
    Same I/O as the insert node but with maskMode='remove'; prompt is optional."""

    _MASK_MODE = "remove"

    @classmethod
    def INPUT_TYPES(s):
        spec = super().INPUT_TYPES()
        spec["required"]["prompt"] = ("STRING", {"multiline": True, "default": ""})
        return spec


NODE_CLASS_MAPPINGS = {
    "Veo3VertexAINode": Veo3VertexAINode,
    "Veo3FirstLastFrameVertexAINode": Veo3FirstLastFrameVertexAINode,
    "Veo3ExtendVertexAINode": Veo3ExtendVertexAINode,
    "Veo3ReferenceSubjectVertexAINode": Veo3ReferenceSubjectVertexAINode,
    "VeoReferenceStyleVertexAINode": VeoReferenceStyleVertexAINode,
    "VeoInpaintInsertVertexAINode": VeoInpaintInsertVertexAINode,
    "VeoInpaintRemoveVertexAINode": VeoInpaintRemoveVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Veo3VertexAINode": "Veo3 Video Generator (Vertex AI)",
    "Veo3FirstLastFrameVertexAINode": "Veo3 First-Last Frame (Vertex AI)",
    "Veo3ExtendVertexAINode": "Veo3 Video Extension (Vertex AI)",
    "Veo3ReferenceSubjectVertexAINode": "Veo3 Reference Subject (Vertex AI)",
    "VeoReferenceStyleVertexAINode": "Veo Reference Style (Vertex AI, Veo 2)",
    "VeoInpaintInsertVertexAINode": "Veo Inpaint Insert (Vertex AI, Veo 2)",
    "VeoInpaintRemoveVertexAINode": "Veo Inpaint Remove (Vertex AI, Veo 2)",
}
