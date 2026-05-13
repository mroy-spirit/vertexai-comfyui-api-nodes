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


class _VeoBase:
    """Shared auth, image conversion, label logging, polling and download helpers."""

    def get_access_token(self) -> str:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token

    def _tensor_to_base64(self, tensor: torch.Tensor) -> str:
        """float32 tensor [H, W, C] → base64-encoded PNG string."""
        np_image = (tensor.numpy() * 255).clip(0, 255).astype(np.uint8)
        pil_image = Image.fromarray(np_image)
        buf = BytesIO()
        pil_image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

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
            f"https://{gcp_location}-aiplatform.googleapis.com"
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
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "enhance_prompt": ("BOOLEAN", {"default": True}),
                "image": ("IMAGE",),
                "labels_json": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": 'JSON labels for Cloud Logging / BigQuery tracking. Example: {"env": "prod"}',
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("local_video_path",)
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
        labels_json="",
    ):
        if resolution == "4k" and model_id in ("veo-3.0-generate-001", "veo-3.0-fast-generate-001"):
            return ("ERROR: 4K resolution is not supported by Veo 3.0 models.",)

        try:
            access_token = self.get_access_token()
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return (f"ERROR: Authentication failed: {e}",)

        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_id, gcp_project, gcp_location)

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
            f"https://{gcp_location}-aiplatform.googleapis.com"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model_id}:predictLongRunning"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"instances": instances, "parameters": parameters}
        logger.info(f"Sending request → {url}\n{json.dumps(payload, indent=2)}")

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            operation_id = resp.json().get("name")
            if not operation_id:
                return ("ERROR: No operation ID in submission response.",)
            logger.info(f"Job started. Operation ID: {operation_id}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on submission: {e}\n{e.response.text}")
            return (f"ERROR: HTTP {e.response.status_code} on submission.",)
        except Exception as e:
            logger.error(f"Submission failed: {e}")
            return (f"ERROR: {e}",)

        try:
            gcs_uri = self.poll_operation(operation_id, gcp_project, gcp_location, model_id, access_token)
        except Exception as e:
            logger.error(str(e))
            return (f"ERROR: {e}",)

        try:
            output_dir = folder_paths.get_temp_directory()
            local_path = os.path.join(output_dir, os.path.basename(gcs_uri))
            self.download_gcs_file(gcs_uri, local_path, access_token)
            return (local_path,)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return (f"ERROR: Download failed: {e}",)


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
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
                "negative_prompt": ("STRING", {"multiline": True, "default": ""}),
                "labels_json": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "tooltip": 'JSON labels for Cloud Logging / BigQuery tracking. Example: {"env": "prod"}',
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("local_video_path",)
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
        labels_json="",
    ):
        if resolution == "4k" and "lite" in model_id:
            return ("ERROR: 4K resolution is not supported by veo-3.1-lite.",)

        try:
            access_token = self.get_access_token()
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return (f"ERROR: Authentication failed: {e}",)

        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_id, gcp_project, gcp_location)

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
            "enhancePrompt": True,  # always True for Veo 3
            "resolution": resolution,
        }
        if negative_prompt and negative_prompt.strip():
            parameters["negativePrompt"] = negative_prompt
        if seed > 0:
            parameters["seed"] = seed

        url = (
            f"https://{gcp_location}-aiplatform.googleapis.com"
            f"/v1/projects/{gcp_project}/locations/{gcp_location}"
            f"/publishers/google/models/{model_id}:predictLongRunning"
        )
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {"instances": [instance], "parameters": parameters}
        logger.info(f"Sending request → {url}")

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            operation_id = resp.json().get("name")
            if not operation_id:
                return ("ERROR: No operation ID in submission response.",)
            logger.info(f"Job started. Operation ID: {operation_id}")
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on submission: {e}\n{e.response.text}")
            return (f"ERROR: HTTP {e.response.status_code} on submission.",)
        except Exception as e:
            logger.error(f"Submission failed: {e}")
            return (f"ERROR: {e}",)

        try:
            gcs_uri = self.poll_operation(operation_id, gcp_project, gcp_location, model_id, access_token)
        except Exception as e:
            logger.error(str(e))
            return (f"ERROR: {e}",)

        try:
            output_dir = folder_paths.get_temp_directory()
            local_path = os.path.join(output_dir, os.path.basename(gcs_uri))
            self.download_gcs_file(gcs_uri, local_path, access_token)
            return (local_path,)
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return (f"ERROR: Download failed: {e}",)


NODE_CLASS_MAPPINGS = {
    "Veo3VertexAINode": Veo3VertexAINode,
    "Veo3FirstLastFrameVertexAINode": Veo3FirstLastFrameVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Veo3VertexAINode": "Veo3 Video Generator (Vertex AI)",
    "Veo3FirstLastFrameVertexAINode": "Veo3 First-Last Frame (Vertex AI)",
}
