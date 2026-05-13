from google.genai.types import EditImageConfig, RawReferenceImage
from .base import _Imagen4EditBase


class MaskFreeEditVertexAINode(_Imagen4EditBase):

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                **cls._gcp_inputs(),
                "image": ("IMAGE",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": cls._common_optional(),
        }

    def execute(
        self, gcp_project, gcp_location, model_name,
        image, prompt,
        seed=0, number_of_images=1,
        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
        person_generation="DONT_ALLOW", labels_json="",
    ):
        labels = self._parse_labels(labels_json)
        if labels:
            self._log_labels(labels, model_name, gcp_project, gcp_location, "maskfree_edit_request")

        client = self._get_client(gcp_project, gcp_location)
        raw_ref = RawReferenceImage(
            reference_id=0,
            reference_image=self._pil_to_genai(self._tensor_to_pil(image)),
        )
        config = EditImageConfig(
            edit_mode="EDIT_MODE_DEFAULT",
            number_of_images=number_of_images,
            seed=seed if seed > 0 else None,
            safety_filter_level=safety_filter_level,
            person_generation=person_generation,
        )
        return (self._call_edit(client, model_name, prompt, [raw_ref], config),)


NODE_CLASS_MAPPINGS = {
    "MaskFreeEditVertexAINode": MaskFreeEditVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MaskFreeEditVertexAINode": "Mask-Free Edit (Vertex AI)",
}
