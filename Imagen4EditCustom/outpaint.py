from PIL import Image as PIL_Image, ImageDraw as PIL_ImageDraw

from google.genai.types import EditImageConfig, MaskReferenceConfig, MaskReferenceImage, RawReferenceImage

from .base import _Imagen4EditBase


class OutpaintingVertexAINode(_Imagen4EditBase):

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("outpainted_image", "outpaint_mask")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": "A beautiful expansive view continuing from the original image."}),
                "target_width": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 8}),
                "target_height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 8}),
                "horizontal_placement": (["left", "center", "right"], {"default": "center"}),
                "vertical_placement": (["top", "center", "bottom"], {"default": "center"}),
                "mask_dilation": ("FLOAT", {"default": 0.03, "min": 0.0, "max": 1.0, "step": 0.001}),
            },
            "optional": cls._common_optional(),
        }

    def _build_padded_image_and_mask(
        self,
        src_pil: PIL_Image.Image,
        target_width: int,
        target_height: int,
        h_placement: str,
        v_placement: str,
    ):
        w, h = src_pil.size
        if target_width < w or target_height < h:
            raise ValueError(
                f"Target dimensions ({target_width}x{target_height}) must be >= source ({w}x{h})."
            )

        x = {"left": 0, "center": (target_width - w) // 2, "right": target_width - w}[h_placement]
        y = {"top": 0, "center": (target_height - h) // 2, "bottom": target_height - h}[v_placement]

        canvas = PIL_Image.new("RGB", (target_width, target_height), (0, 0, 0))
        canvas.paste(src_pil.convert("RGB"), (x, y))

        mask = PIL_Image.new("L", (target_width, target_height), 255)
        PIL_ImageDraw.Draw(mask).rectangle([x, y, x + w, y + h], fill=0)

        return canvas, mask

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, prompt, target_width, target_height,
        horizontal_placement, vertical_placement, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", custom_label_key="", custom_label_value="",
    ):
        self._log_labels(self._parse_labels(custom_label_key, custom_label_value), model_name, gcp_project, gcp_location, "outpaint_request")

        src_pil = self._tensor_to_pil(image)
        canvas_pil, mask_pil = self._build_padded_image_and_mask(
            src_pil, target_width, target_height, horizontal_placement, vertical_placement
        )

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(canvas_pil))
        mask_ref = MaskReferenceImage(
            reference_id=1,
            reference_image=self._pil_to_genai(mask_pil),
            config=MaskReferenceConfig(
                mask_mode="MASK_MODE_USER_PROVIDED",
                mask_dilation=mask_dilation,
            ),
        )
        config = EditImageConfig(
            edit_mode="EDIT_MODE_OUTPAINT",
            number_of_images=number_of_images,
            seed=seed if seed > 0 else None,
            safety_filter_level=safety_filter_level,
            person_generation=person_generation,
        )
        out_image = self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config)
        out_mask = self._pil_to_mask_tensor(mask_pil)
        return (out_image, out_mask)


NODE_CLASS_MAPPINGS = {
    "OutpaintingVertexAINode": OutpaintingVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OutpaintingVertexAINode": "Outpainting (Vertex AI)",
}
