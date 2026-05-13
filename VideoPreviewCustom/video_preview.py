import logging
import os

import folder_paths

logger = logging.getLogger(__name__)


class VideoPreviewVertexAINode:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "local_video_path": ("STRING",),
            }
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def execute(self, local_video_path: str):
        output_dir = folder_paths.get_output_directory()
        temp_dir = folder_paths.get_temp_directory()

        abs_path = os.path.realpath(local_video_path)
        filename = os.path.basename(abs_path)

        if abs_path.startswith(os.path.realpath(output_dir)):
            file_type = "output"
            base = os.path.realpath(output_dir)
        elif abs_path.startswith(os.path.realpath(temp_dir)):
            file_type = "temp"
            base = os.path.realpath(temp_dir)
        else:
            # File is outside ComfyUI dirs — copy to output so /view can serve it
            import shutil
            dest = os.path.join(output_dir, filename)
            shutil.copy2(abs_path, dest)
            abs_path = dest
            file_type = "output"
            base = os.path.realpath(output_dir)

        rel = os.path.relpath(os.path.dirname(abs_path), base)
        subfolder = "" if rel == "." else rel

        return {"ui": {"videos": [{"filename": filename, "subfolder": subfolder, "type": file_type}]}}


NODE_CLASS_MAPPINGS = {
    "VideoPreviewVertexAINode": VideoPreviewVertexAINode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "VideoPreviewVertexAINode": "Video Preview (Vertex AI)",
}
