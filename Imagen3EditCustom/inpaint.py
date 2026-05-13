from google.genai.types import EditImageConfig, RawReferenceImage
from .base import _Imagen4EditBase

_AUTO_MASK_MODES = ["MASK_MODE_FOREGROUND", "MASK_MODE_BACKGROUND"]


def _inpaint_config(mode, number_of_images, seed, safety_filter_level, person_generation):
    return EditImageConfig(
        edit_mode=mode,
        number_of_images=number_of_images,
        seed=seed if seed > 0 else None,
        safety_filter_level=safety_filter_level,
        person_generation=person_generation,
    )


# ------------------------------------------------------------------ #
# Inpaint Insert                                                       #
# ------------------------------------------------------------------ #

class InpaintInsertMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, mask, prompt, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "inpaint_insert_mask_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(self._tensor_to_pil(image)))
        mask_ref = self._make_manual_mask_ref(mask, mask_dilation)
        config = _inpaint_config("EDIT_MODE_INPAINT_INSERTION", number_of_images, seed, safety_filter_level, person_generation)
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


class InpaintInsertAutoMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "mask_mode": (_AUTO_MASK_MODES,),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, prompt, mask_mode, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "inpaint_insert_automask_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(self._tensor_to_pil(image)))
        mask_ref = self._make_auto_mask_ref(mask_mode, mask_dilation)
        config = _inpaint_config("EDIT_MODE_INPAINT_INSERTION", number_of_images, seed, safety_filter_level, person_generation)
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


class InpaintInsertSemanticMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "semantic_classes_csv": ("STRING", {"default": "0", "tooltip": "Comma-separated class IDs to mask, e.g. 0,1,2"}),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, prompt, semantic_classes_csv, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "inpaint_insert_semantic_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(self._tensor_to_pil(image)))
        mask_ref = self._make_semantic_mask_ref(semantic_classes_csv, mask_dilation)
        config = _inpaint_config("EDIT_MODE_INPAINT_INSERTION", number_of_images, seed, safety_filter_level, person_generation)
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


# ------------------------------------------------------------------ #
# Inpaint Remove                                                       #
# ------------------------------------------------------------------ #

class InpaintRemoveMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, mask, prompt, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "inpaint_remove_mask_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(self._tensor_to_pil(image)))
        mask_ref = self._make_manual_mask_ref(mask, mask_dilation)
        config = _inpaint_config("EDIT_MODE_INPAINT_REMOVAL", number_of_images, seed, safety_filter_level, person_generation)
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


class InpaintRemoveAutoMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "mask_mode": (_AUTO_MASK_MODES,),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, prompt, mask_mode, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "inpaint_remove_automask_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(self._tensor_to_pil(image)))
        mask_ref = self._make_auto_mask_ref(mask_mode, mask_dilation)
        config = _inpaint_config("EDIT_MODE_INPAINT_REMOVAL", number_of_images, seed, safety_filter_level, person_generation)
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


class InpaintRemoveSemanticMaskVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "semantic_classes_csv": ("STRING", {"default": "0", "tooltip": "Comma-separated class IDs to remove, e.g. 0,1,2"}),
                "mask_dilation": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, prompt, semantic_classes_csv, mask_dilation,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "inpaint_remove_semantic_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(reference_id=0, reference_image=self._pil_to_genai(self._tensor_to_pil(image)))
        mask_ref = self._make_semantic_mask_ref(semantic_classes_csv, mask_dilation)
        config = _inpaint_config("EDIT_MODE_INPAINT_REMOVAL", number_of_images, seed, safety_filter_level, person_generation)
        return (self._call_edit(client, model_name, prompt, [raw_ref, mask_ref], config),)


NODE_CLASS_MAPPINGS = {
    "InpaintInsertMaskVertexAINode": InpaintInsertMaskVertexAINode,
    "InpaintInsertAutoMaskVertexAINode": InpaintInsertAutoMaskVertexAINode,
    "InpaintInsertSemanticMaskVertexAINode": InpaintInsertSemanticMaskVertexAINode,
    "InpaintRemoveMaskVertexAINode": InpaintRemoveMaskVertexAINode,
    "InpaintRemoveAutoMaskVertexAINode": InpaintRemoveAutoMaskVertexAINode,
    "InpaintRemoveSemanticMaskVertexAINode": InpaintRemoveSemanticMaskVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "InpaintInsertMaskVertexAINode": "Inpaint Insert - Manual Mask (Vertex AI)",
    "InpaintInsertAutoMaskVertexAINode": "Inpaint Insert - Auto Mask (Vertex AI)",
    "InpaintInsertSemanticMaskVertexAINode": "Inpaint Insert - Semantic Mask (Vertex AI)",
    "InpaintRemoveMaskVertexAINode": "Inpaint Remove - Manual Mask (Vertex AI)",
    "InpaintRemoveAutoMaskVertexAINode": "Inpaint Remove - Auto Mask (Vertex AI)",
    "InpaintRemoveSemanticMaskVertexAINode": "Inpaint Remove - Semantic Mask (Vertex AI)",
}
