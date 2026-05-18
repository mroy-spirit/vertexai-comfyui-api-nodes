# ComfyUI Custom Nodes for Google Vertex AI

Custom ComfyUI nodes that call Google Vertex AI models **directly** using Application Default Credentials (ADC). Designed to run on a **Google Compute Engine VM** — no `gcloud` CLI required at runtime, no key files, no manual authentication. The VM's attached service account is used automatically.

## Attribution

This project is based on and adapted from:

- **[NucleusEngineering/vertexai-comfyui-api-nodes](https://github.com/NucleusEngineering/vertexai-comfyui-api-nodes)** — original Vertex AI ComfyUI integration
- **[GoogleCloudPlatform/professional-services — comfyui_custom_nodes](https://github.com/GoogleCloudPlatform/professional-services/tree/main/tools/comfyui_custom_nodes)** — reference implementations for Imagen3 editing (bg swap, inpaint, outpaint, mask-free), Gemini text, and video preview nodes
- **[comfyanonymous/ComfyUI — API nodes](https://github.com/comfyanonymous/ComfyUI)** — reference implementations for the Gemini and Veo node patterns

---

## Nodes

### Generation

| Node | Category | Description |
|---|---|---|
| **Imagen4 Image Generator (Vertex AI)** | VertexAI | Generate images with Imagen 4 via Vertex AI REST API |
| **Veo3 Video Generator (Vertex AI)** | VertexAI | Generate videos from text or image with Veo 3.x models |
| **Veo3 First-Last Frame (Vertex AI)** | VertexAI | Interpolate video between a first and last frame |
| **Veo3 Video Extension (Vertex AI)** | VertexAI | Extend an existing Veo-generated MP4 by ~7 s (Veo 3.1) |
| **Veo3 Reference Subject (Vertex AI)** | VertexAI | Generate a video conditioned on 1–3 subject reference images (Veo 3.1) |
| **Veo Reference Style (Vertex AI, Veo 2)** | VertexAI | Generate a video in the style of a single reference image (Veo 2 only) |
| **Veo Inpaint Insert (Vertex AI, Veo 2)** | VertexAI | Insert an object into a masked region of an existing video (Veo 2 only) |
| **Veo Inpaint Remove (Vertex AI, Veo 2)** | VertexAI | Remove an object from a masked region of an existing video (Veo 2 only) |
| **Gemini (Vertex AI)** | VertexAI | Generate images (and optionally text) with Gemini image models |
| **Gemini Text (Vertex AI)** | VertexAI | Generate text with Gemini models; supports optional image/video inputs |

### Imagen4 Editing

All editing nodes use model `imagen-4.0-capability-001` by default (user-editable STRING).

| Node | Category | Description |
|---|---|---|
| **BG Swap - Manual Mask (Vertex AI)** | VertexAI/Imagen4 | Replace background using a provided mask |
| **BG Swap - Auto Mask (Vertex AI)** | VertexAI/Imagen4 | Replace background with automatic background detection |
| **Inpaint Insert - Manual Mask (Vertex AI)** | VertexAI/Imagen4 | Insert content into masked region |
| **Inpaint Insert - Auto Mask (Vertex AI)** | VertexAI/Imagen4 | Insert content with auto foreground/background mask |
| **Inpaint Insert - Semantic Mask (Vertex AI)** | VertexAI/Imagen4 | Insert content over semantic class regions |
| **Inpaint Remove - Manual Mask (Vertex AI)** | VertexAI/Imagen4 | Remove content in masked region |
| **Inpaint Remove - Auto Mask (Vertex AI)** | VertexAI/Imagen4 | Remove content with auto foreground/background mask |
| **Inpaint Remove - Semantic Mask (Vertex AI)** | VertexAI/Imagen4 | Remove content in semantic class regions |
| **Mask-Free Edit (Vertex AI)** | VertexAI/Imagen4 | Edit image with prompt only, no mask required |
| **Outpainting (Vertex AI)** | VertexAI/Imagen4 | Extend image beyond its original borders |

### Utilities

| Node | Category | Description |
|---|---|---|
| **Video Preview (Vertex AI)** | VertexAI | Preview a local video file inline in ComfyUI |
| **Image to Base64 (Vertex AI)** | VertexAI | Convert a ComfyUI IMAGE tensor to a base64 PNG string |

---

## Prerequisites

### On a GCE VM
No extra setup. The VM's service account provides credentials automatically via the metadata server. Grant it the required IAM roles:

```
Vertex AI User            (roles/aiplatform.user)
Storage Object Viewer     (roles/storage.objectViewer)   ← Veo nodes download from GCS
```

> **Note on access scopes:** The VM must have the `cloud-platform` access scope enabled. If you see `403 insufficient authentication scopes`, stop the VM, edit its service account settings and enable "Allow full access to all Cloud APIs", then restart.

### On a local machine
Install the Google Cloud SDK and run:
```bash
gcloud auth application-default login
```

---

## Installation

Clone into your ComfyUI `custom_nodes` directory and install all dependencies:

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/mroy-spirit/vertexai-comfyui-api-nodes.git
pip install -r vertexai-comfyui-api-nodes/requirements.txt
```

Restart ComfyUI. All nodes appear under the **VertexAI** category.

---

## Node Reference

### Imagen4 Image Generator (Vertex AI)

Generates images using the Imagen 4 REST API. Supports batched output (up to 4 images).

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region (e.g. `us-central1`) or `global` for preview models |
| `model_name` | COMBO | ✅ | `imagen-4.0-generate-001` or `imagen-4.0-ultra-generate-001` |
| `prompt` | STRING | ✅ | Generation prompt |
| `negative_prompt` | STRING | | What to avoid |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `number_of_images` | INT | | 1–4 images per request |
| `aspect_ratio` | COMBO | | `1:1`, `5:4`, `3:2`, `7:4`, `4:3`, `16:9`, `9:16` |
| `sample_image_size` | COMBO | | `1K` (default) or `2K` |
| `guidance_scale` | FLOAT | | 0–30, how strongly the prompt is followed |
| `person_generation` | COMBO | | `dont_allow`, `allow_adult`, `allow_all` |
| `safety_filter_level` | COMBO | | `block_low_and_above`, `block_medium_and_above`, `block_only_high`, `block_none` |
| `add_watermark` | BOOLEAN | | Add SynthID watermark (default: False) |
| `labels_json` | STRING | | JSON labels for BigQuery tracking (see below) |

**Output:** `IMAGE` (batch tensor)

---

### Veo3 Video Generator (Vertex AI)

Generates videos using the Veo 3.x REST API. Submits a long-running job, polls until complete, downloads the result from GCS to the ComfyUI output directory.

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
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `image` | IMAGE | | Optional reference image (image-to-video) |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

Connect the local file path to **Video Preview (Vertex AI)** to preview inline.

---

### Veo3 First-Last Frame (Vertex AI)

Generates a video that transitions between a first and last frame. Requires Veo 3.1 models.

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
| `resolution` | COMBO | | `720p`, `1080p`, `4k` (not available on lite) |
| `generate_audio` | BOOLEAN | | Generate audio track |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

---

### Veo3 Video Extension (Vertex AI)

Extends an existing Veo-generated MP4 by ~7 seconds. Chain multiple extension nodes to build longer videos (up to ~141 s total). The input video must already be Veo-generated and must be a `gs://` URI — the API does not accept base64 video, so the easiest pattern is to wire the `gcs_uri` output of a previous Veo node into `input_video_gcs_uri`. Veo 3.1 only.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | ✅ | What should happen in the extended segment |
| `storage_uri` | STRING | ✅ | GCS output path |
| `input_video_gcs_uri` | STRING | ✅ | `gs://` URI of the Veo-generated MP4 to extend |
| `model_id` | COMBO | | `veo-3.1-generate-001`, `veo-3.1-fast-generate-001`, `veo-3.1-lite-generate-001` |
| `aspect_ratio` | COMBO | | `16:9` or `9:16` |
| `resolution` | COMBO | | `720p`, `1080p`, `4k` (not available on lite) |
| `generate_audio` | BOOLEAN | | Generate audio track |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `custom_label_key` / `custom_label_value` | STRING | | Optional per-node label for BigQuery tracking |

**Note:** Output length is fixed at 7 s per call by the API, so this node has no `duration_seconds` input.

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

---

### Veo3 Reference Subject (Vertex AI)

Generates an 8-second video conditioned on 1–3 subject reference images (people, objects, etc.). Veo 3.1.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | ✅ | Video description referring to the subject |
| `storage_uri` | STRING | ✅ | GCS output path |
| `reference_image_1` | IMAGE | ✅ | First subject reference image |
| `reference_image_2` | IMAGE | | Second subject reference (optional) |
| `reference_image_3` | IMAGE | | Third subject reference (optional) |
| `model_id` | COMBO | | `veo-3.1-generate-001`, `veo-3.1-fast-generate-001`, `veo-3.1-lite-generate-001` |
| `aspect_ratio` | COMBO | | `16:9` or `9:16` |
| `resolution` | COMBO | | `720p`, `1080p`, `4k` (not available on lite) |
| `generate_audio` | BOOLEAN | | Generate audio track |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `custom_label_key` / `custom_label_value` | STRING | | Optional per-node label for BigQuery tracking |

**Note:** Duration is locked to 8 s by the Vertex API whenever `referenceImages` is set, so this node has no `duration_seconds` input.

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

---

### Veo Reference Style (Vertex AI, Veo 2)

Generates an 8-second video in the style of a single reference image. **Veo 2 only** — Veo 3.1 does not support style references.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | ✅ | Video description |
| `storage_uri` | STRING | ✅ | GCS output path |
| `style_reference_image` | IMAGE | ✅ | Style reference (a single image) |
| `model_id` | COMBO | | `veo-2.0-generate-001`, `veo-2.0-generate-exp`, `veo-2.0-generate-preview` |
| `aspect_ratio` | COMBO | | `16:9` or `9:16` |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `custom_label_key` / `custom_label_value` | STRING | | Optional per-node label for BigQuery tracking |

**Note:** Veo 2 does not support `generate_audio`, `resolution`, or custom `duration_seconds` (locked to 8 s).

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

---

### Veo Inpaint Insert (Vertex AI, Veo 2)

Inserts an object described by the prompt into the white region of a MASK over an existing video. **Veo 2 only.** The input video must be a `gs://` URI; the mask is a standard ComfyUI MASK tensor (white = region to fill).

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | ✅ | What to insert into the masked region |
| `storage_uri` | STRING | ✅ | GCS output path |
| `input_video_gcs_uri` | STRING | ✅ | `gs://` URI of the MP4 to edit |
| `mask` | MASK | ✅ | ComfyUI mask, white = region to fill |
| `model_id` | COMBO | | `veo-2.0-generate-001`, `veo-2.0-generate-exp`, `veo-2.0-generate-preview` |
| `aspect_ratio` | COMBO | | `16:9` or `9:16` |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `custom_label_key` / `custom_label_value` | STRING | | Optional per-node label for BigQuery tracking |

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

---

### Veo Inpaint Remove (Vertex AI, Veo 2)

Removes content from the white region of a MASK over an existing video and fills it in. **Veo 2 only.** Identical inputs to the Insert node, but `prompt` is optional — removal doesn't always need one.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region |
| `prompt` | STRING | | Optional hint for what should appear in the filled region |
| `storage_uri` | STRING | ✅ | GCS output path |
| `input_video_gcs_uri` | STRING | ✅ | `gs://` URI of the MP4 to edit |
| `mask` | MASK | ✅ | ComfyUI mask, white = region to remove |
| `model_id` | COMBO | | `veo-2.0-generate-001`, `veo-2.0-generate-exp`, `veo-2.0-generate-preview` |
| `aspect_ratio` | COMBO | | `16:9` or `9:16` |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `negative_prompt` | STRING | | What to avoid |
| `enhance_prompt` | BOOLEAN | | AI prompt enhancement |
| `custom_label_key` / `custom_label_value` | STRING | | Optional per-node label for BigQuery tracking |

**Outputs:** `STRING` (local file path), `STRING` (GCS URI `gs://...`)

---

### Gemini (Vertex AI)

Generates images (and optionally text) using Gemini image models via the Vertex AI REST API.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region or `global` |
| `model` | COMBO | ✅ | `gemini-3.1-flash-image-preview` or `gemini-3-pro-image-preview` |
| `prompt` | STRING | ✅ | Generation prompt |
| `seed` | INT | | Reproducibility seed (0 = random) |
| `aspect_ratio` | COMBO | | `auto`, `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`, `1:4`, `4:1`, `8:1`, `1:8` |
| `resolution` | COMBO | | `1K`, `2K`, `4K` |
| `response_modalities` | COMBO | | `IMAGE+TEXT` or `IMAGE` |
| `thinking_level` | COMBO | | `MINIMAL` (no thinking overhead) or `HIGH` (extended thinking, pro model only) |
| `images` | IMAGE | | Up to 14 reference images |
| `system_prompt` | STRING | | System-level instruction |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Outputs:** `IMAGE` (generated image), `STRING` (text response), `IMAGE` (thought image, only with `HIGH` thinking)

---

### Gemini Text (Vertex AI)

Generates text using any Gemini model. Supports optional image and video inputs for multimodal prompts.

| Input | Type | Required | Description |
|---|---|---|---|
| `gcp_project` | STRING | ✅ | GCP project ID |
| `gcp_location` | STRING | ✅ | Region or `global` |
| `model` | STRING | ✅ | Model name (default: `gemini-2.0-flash-001`) |
| `prompt` | STRING | ✅ | Text prompt |
| `temperature` | FLOAT | | 0–2, sampling temperature (default: 0.9) |
| `top_p` | FLOAT | | 0–1, nucleus sampling |
| `top_k` | INT | | 1–40, top-k sampling |
| `max_output_tokens` | INT | | 1–8192 (default: 2048) |
| `stop_sequences` | STRING | | Comma-separated stop sequences |
| `image` | IMAGE | | Optional image for multimodal prompt |
| `video_urls` | STRING | | One GCS video URL per line (`gs://...`) |
| `labels_json` | STRING | | JSON labels for BigQuery tracking |

**Output:** `STRING` (generated text)

---

### Imagen4 Editing Nodes

All editing nodes share the same common inputs:

**Required (all editing nodes):**

| Input | Type | Description |
|---|---|---|
| `gcp_project` | STRING | GCP project ID |
| `gcp_location` | STRING | Region (e.g. `us-central1`) |
| `model_name` | STRING | Edit model name (default: `imagen-4.0-capability-001`) |

**Optional (all editing nodes):**

| Input | Type | Description |
|---|---|---|
| `seed` | INT | 0 = random, otherwise fixes output |
| `number_of_images` | INT | 1–4 output images |
| `safety_filter_level` | COMBO | `BLOCK_LOW_AND_ABOVE`, `BLOCK_MEDIUM_AND_ABOVE`, `BLOCK_ONLY_HIGH`, `BLOCK_NONE` |
| `person_generation` | COMBO | `DONT_ALLOW`, `ALLOW_ADULT`, `ALLOW_ALL` |
| `labels_json` | STRING | JSON labels for BigQuery tracking |

#### BG Swap - Manual Mask (Vertex AI)

Replaces the background in the region defined by the provided mask.

Additional inputs: `product_image` IMAGE, `mask` MASK, `prompt` STRING, `mask_dilation` FLOAT

**Output:** `IMAGE`

#### BG Swap - Auto Mask (Vertex AI)

Replaces the background using automatic background detection — no mask required.

Additional inputs: `product_image` IMAGE, `prompt` STRING, `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Inpaint Insert - Manual Mask (Vertex AI)

Inserts content described by the prompt into the white region of the provided mask.

Additional inputs: `image` IMAGE, `mask` MASK, `prompt` STRING, `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Inpaint Insert - Auto Mask (Vertex AI)

Inserts content into the foreground or background region, detected automatically.

Additional inputs: `image` IMAGE, `prompt` STRING, `mask_mode` COMBO (`MASK_MODE_FOREGROUND` / `MASK_MODE_BACKGROUND`), `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Inpaint Insert - Semantic Mask (Vertex AI)

Inserts content into regions belonging to specified semantic class IDs.

Additional inputs: `image` IMAGE, `prompt` STRING, `semantic_classes_csv` STRING (e.g. `"0,1,2"`), `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Inpaint Remove - Manual Mask (Vertex AI)

Removes content in the masked region and fills it in.

Additional inputs: `image` IMAGE, `mask` MASK, `prompt` STRING, `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Inpaint Remove - Auto Mask (Vertex AI)

Removes the foreground or background region detected automatically.

Additional inputs: `image` IMAGE, `prompt` STRING, `mask_mode` COMBO, `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Inpaint Remove - Semantic Mask (Vertex AI)

Removes content in regions belonging to specified semantic class IDs.

Additional inputs: `image` IMAGE, `prompt` STRING, `semantic_classes_csv` STRING, `mask_dilation` FLOAT

**Output:** `IMAGE`

#### Mask-Free Edit (Vertex AI)

Edits the image based on the prompt alone, without any mask.

Additional inputs: `image` IMAGE, `prompt` STRING

**Output:** `IMAGE`

#### Outpainting (Vertex AI)

Extends the image beyond its original borders to fill a larger canvas.

Additional inputs: `image` IMAGE, `prompt` STRING, `target_width` INT, `target_height` INT, `horizontal_placement` COMBO (`left`/`center`/`right`), `vertical_placement` COMBO (`top`/`center`/`bottom`), `mask_dilation` FLOAT

**Outputs:** `IMAGE` (outpainted result), `MASK` (the outpaint region mask)

---

### Video Preview (Vertex AI)

Displays a local video file inline in the ComfyUI node graph. Connect the `local_video_path` output from a Veo3 node directly.

| Input | Type | Description |
|---|---|---|
| `local_video_path` | STRING | Path to a local video file |

This is an output node (no tensor outputs). Right-click the node to open or save the preview.

---

### Image to Base64 (Vertex AI)

Converts a ComfyUI IMAGE tensor to a base64-encoded PNG string. Useful for passing images to REST APIs or storing them as strings.

| Input | Type | Description |
|---|---|---|
| `image` | IMAGE | ComfyUI image tensor |

**Output:** `STRING` (base64-encoded PNG)

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
