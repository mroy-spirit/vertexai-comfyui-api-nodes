from google.genai.types import EditImageConfig, RawReferenceImage
from .base import _Imagen4EditBase


class BGSwapMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "product_image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"multiline": True, "default": "A clean studio background"}),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        product_image, mask, prompt, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", custom_label_key="", custom_label_value="",
    ):
        self._log_labels(self._parse_labels(custom_label_key, custom_label_value), model_name, gcp_project, gcp_location, "bgswap_mask_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(
            reference_id=0,
            reference_image=self._pil_to_genai(self._tensor_to_pil(product_image)),
        )
        mask_ref = self._make_manual_mask_ref(mask, mask_dilation)
        config = EditImageConfig(
            edit_mode="EDIT_MODE_BGSWAP",
            number_of_images=number_of_images,
            seed=seed if seed > 0 else None,
            safety_filter_level=safety_filter_level,
            person_generation=person_generation,
        )
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


class BGSwapAutoMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "product_image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": "A clean studio background"}),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        product_image, prompt, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", custom_label_key="", custom_label_value="",
    ):
        self._log_labels(self._parse_labels(custom_label_key, custom_label_value), model_name, gcp_project, gcp_location, "bgswap_automask_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(
            reference_id=0,
            reference_image=self._pil_to_genai(self._tensor_to_pil(product_image)),
        )
        mask_ref = self._make_auto_mask_ref("MASK_MODE_BACKGROUND", mask_dilation)
        config = EditImageConfig(
            edit_mode="EDIT_MODE_BGSWAP",
            number_of_images=number_of_images,
            seed=seed if seed > 0 else None,
            safety_filter_level=safety_filter_level,
            person_generation=person_generation,
        )
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


NODE_CLASS_MAPPINGS = {
    "BGSwapMaskVertexAINode": BGSwapMaskVertexAINode,
    "BGSwapAutoMaskVertexAINode": BGSwapAutoMaskVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "BGSwapMaskVertexAINode": "BG Swap - Manual Mask (Vertex AI)",
    "BGSwapAutoMaskVertexAINode": "BG Swap - Auto Mask (Vertex AI)",
}
