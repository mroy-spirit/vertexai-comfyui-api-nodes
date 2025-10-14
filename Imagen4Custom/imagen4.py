import torch
import numpy as np
from PIL import Image
import os

from google.cloud import aiplatform
import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

class Imagen4:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "vertex-ai-model-location")}),
                "model_name": ("STRING", {"default": "imagen-4.0-generate-001"}),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "A beautiful landscape"
                }),
                "negative_prompt": ("STRING", {
                    "multiline": True,
                    "default": ""
                }),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(self, gcp_project, gcp_location, model_name, prompt, negative_prompt, seed):
        try:
            vertexai.init(project=gcp_project, location=gcp_location)
            model = ImageGenerationModel.from_pretrained(model_name)
            logging.info("Vertex AI initialized successfully for this generation.")

            logging.info(f"Generating image with prompt: {prompt}")
            response = model.generate_images(
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=seed,
                number_of_images=1,
                add_watermark=False
            )

            if not response.images:
                raise RuntimeError("The API did not return any images.")

            # The response contains a list of generated images
            generated_image = response.images[0]

            # The image data is in binary format, so we need to load it
            # This assumes the image is a PNG, which is the default
            pil_image = generated_image._pil_image

            # Convert PIL Image to Tensor
            output_image = np.array(pil_image).astype(np.float32) / 255.0
            output_image = torch.from_numpy(output_image)[None,]

            return (output_image,)

        except Exception as e:
            logging.error(f"An error occurred during image generation: {e}")
            # Return a dummy black image in case of an error
            width, height = 512, 512
            image_data = np.zeros((height, width, 3), dtype=np.uint8)
            img = Image.fromarray(image_data, 'RGB')
            
            output_image = np.array(img).astype(np.float32) / 255.0
            output_image = torch.from_numpy(output_image)[None,]
            return (output_image,)


NODE_CLASS_MAPPINGS = {
    "Imagen4VertexAINode": Imagen4
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Imagen4VertexAINode": "Imagen4 Image Generator (Vertex AI)"
}

