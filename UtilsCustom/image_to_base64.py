import base64
import io

import numpy as np
import torch
from PIL import Image as PIL_Image


class ImageToBase64VertexAINode:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("base64_string",)
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(self, image: torch.Tensor):
        img_tensor = image[0] if image.ndim == 4 else image
        np_img = (img_tensor.cpu().numpy().clip(0, 1) * 255).astype(np.uint8)
        pil_img = PIL_Image.fromarray(np_img, "RGB")
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return (base64.b64encode(buf.getvalue()).decode("utf-8"),)


NODE_CLASS_MAPPINGS = {
    "ImageToBase64VertexAINode": ImageToBase64VertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToBase64VertexAINode": "Image to Base64 (Vertex AI)",
}
