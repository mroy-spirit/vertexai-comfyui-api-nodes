# ComfyUI Custom Nodes for Google Vertex AI

Custom ComfyUI nodes that call Google Vertex AI models **directly** using Application Default Credentials (ADC). Designed to run on a **Google Compute Engine VM** — no `gcloud` CLI required at runtime, no key files, no manual authentication. The VM's attached service account is used automatically.

> **Based on** [NucleusEngineering/vertexai-comfyui-api-nodes](https://github.com/NucleusEngineering/vertexai-comfyui-api-nodes).
> The Gemini and Veo reference implementations in this repo are adapted from [comfyanonymous/ComfyUI](https://github.com/comfyanonymous/ComfyUI) API nodes.

## Nodes

| Node | Category | Description |
|---|---|---|
| **Imagen4 Image Generator** | VertexAI | Generate images with Imagen 4 via Vertex AI SDK |
| **Veo3 Video Generator** | VertexAI | Generate videos from text/image with Veo 3.x models |
| **Veo3 First-Last Frame** | VertexAI | Interpolate video between a first and last frame |
| **Gemini (Vertex AI)** | VertexAI | Generate images (and optionally text) with Gemini image models |

---

## Prerequisites

### On a GCE VM
No extra setup. The VM's service account provides credentials automatically via the metadata server. You only need to grant it the right IAM role:

```
Vertex AI User  (roles/aiplatform.user)
Storage Object Viewer  (roles/storage.objectViewer)  ← for Veo nodes that download from GCS
```

### On a local machine
Install the Google Cloud SDK and run:
```bash
gcloud auth application-default login
```

---

## Installation

Clone into your ComfyUI `custom_nodes` directory and install all dependencies in one step:

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/mroy-spirit/vertexai-comfyui-api-nodes.git
pip install -r vertexai-comfyui-api-nodes/requirements.txt
```

Restart ComfyUI. All nodes appear under the **VertexAI** category.

---

## Node Reference

### Imagen4 Image Generator

Generates images using the Imagen 4 Vertex AI SDK. Supports batched output (up to 4 images).

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region (e.g. `us-central1`) |
| `model_name` | COMBO | ✅ | `imagen-4.0-generate-001` or `imagen-4.0-ultra-generate-001` |
| `prompt` | STRING | ✅ | Generation prompt |
| `negative_prompt` | STRING | | What to avoid |
| `seed` | INT | | Reproducibility seed |
| `number_of_images` | INT | | 1–4 images per request |
| `aspect_ratio` | COMBO | | `1:1`, `5:4`, `3:2`, `7:4`, `4:3`, `16:9`, `9:16` |
| `sample_image_size` | COMBO | | `1K` (default) or `2K` |
| `guidance_scale` | FLOAT | | 0–30, how strongly the prompt is followed |
| `person_generation` | COMBO | | `dont_allow`, `allow_none`, `allow_adult`, `allow_all` |
| `safety_filter_level` | COMBO | | `block_low_and_above`, `block_medium_and_above`, `block_only_high`, `block_none` |
| `add_watermark` | BOOLEAN | | Add SynthID watermark (default: False) |
| `labels_json` | STRING | | JSON labels for BigQuery tracking (see below) |

**Output:** `IMAGE` (batch tensor)

---

### Veo3 Video Generator

Generates videos using the Veo 3.x REST API. Submits a long-running job, polls for completion, downloads the result from GCS.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | ✅ | Video description |
| `storage_uri` | STRING | ✅ | GCS output path, e.g. `gs://my-bucket/output/` |
| `model_id` | COMBO | | `veo-3.0-generate-001`, `veo-3.0-fast-generate-001`, `veo-3.1-generate-001`, `veo-3.1-fast-generate-001`, `veo-3.1-lite-generate-001` |
| `aspect_ratio` | COMBO | | `16:9`, `9:16`, `1:1`, `4:5` |
| `duration_seconds` | INT | | 4 or 8 seconds |
| `resolution` | COMBO | | `720p`, `1080p`, `4k` (4k requires Veo 3.1) |
| `generate_audio` | BOOLEAN | | Generate audio track |
| `person_generation` | COMBO | | `allow_all` or `dont_allow` |
| `seed` | INT | | Reproducibility seed |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `image` | IMAGE | | Optional reference image (for image-to-video) |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Output:** `STRING` (local file path to downloaded video)

---

### Veo3 First-Last Frame

Generates a video that transitions between a first and last frame image. Requires Veo 3.1 models.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | ✅ | Video description |
| `storage_uri` | STRING | ✅ | GCS output path |
| `first_frame` | IMAGE | ✅ | Start frame |
| `last_frame` | IMAGE | ✅ | End frame |
| `model_id` | COMBO | | `veo-3.1-generate-001`, `veo-3.1-fast-generate-001`, `veo-3.1-lite-generate-001` |
| `aspect_ratio` | COMBO | | `16:9` or `9:16` |
| `duration_seconds` | INT | | 4 or 8 seconds |
| `resolution` | COMBO | | `720p`, `1080p`, `4k` (4k not available on lite) |
| `generate_audio` | BOOLEAN | | Generate audio track |
| `seed` | INT | | Reproducibility seed |
| `negative_prompt` | STRING | | What to avoid |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Output:** `STRING` (local file path to downloaded video)

---

### Gemini (Vertex AI)

Generates images (and optionally text) using Gemini image models via the Vertex AI REST API directly. Mirrors the `GeminiNanoBanana2V2` node from the ComfyUI API nodes, but uses ADC credentials instead of the ComfyUI proxy.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `model` | COMBO | ✅ | `gemini-3.1-flash-image-preview` (Nano Banana 2) or `gemini-3-pro-image-preview` (Nano Banana Pro) |
| `prompt` | STRING | ✅ | Generation prompt |
| `seed` | INT | | Reproducibility seed |
| `aspect_ratio` | COMBO | | `auto`, `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`, `1:4`, `4:1`, `8:1`, `1:8` |
| `resolution` | COMBO | | `1K`, `2K`, `4K` |
| `response_modalities` | COMBO | | `IMAGE+TEXT` or `IMAGE` |
| `thinking_level` | COMBO | | `MINIMAL` or `HIGH` |
| `images` | IMAGE | | Up to 14 reference images (ingredients) |
| `system_prompt` | STRING | | System-level instruction |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Outputs:** `IMAGE` (generated image), `STRING` (text response), `IMAGE` (thought image, only with `HIGH` thinking)

---

## BigQuery Label Tracking

All nodes accept an optional `labels_json` input — a JSON object of key-value pairs:

```json
{"env": "prod", "workflow": "my-pipeline", "user": "john"}
```

On a GCE VM with Cloud Logging enabled (default), these labels are written as structured log entries and can be routed to BigQuery via [Log Router](https://cloud.google.com/logging/docs/export/configure_export_v2). This lets you track model usage, cost attribution, and request volume per workflow or user.

---

## Preview

![ComfyUI Preview](https://raw.githubusercontent.com/NucleusEngineering/vertexai-comfyui-api-nodes/refs/heads/main/static/sample.png)

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
