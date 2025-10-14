import subprocess
import requests
import json
import time
import os
import folder_paths

class Veo3VertexAINode:
    """
    A ComfyUI custom node to generate videos using Google's Veo3 model via the Vertex AI API.
    This node initiates a job, polls for completion, downloads the result,
    and returns the local file path of the generated video.
    """
    @classmethod
    def INPUT_TYPES(s):
        """
        Defines the input fields for the node in the ComfyUI interface.
        """
        return {
            "required": {
                "gcp_project": ("STRING", {"default": os.environ.get("PROJECT_ID", "vertex-ai-project-id")}),
                "gcp_location": ("STRING", {"default": os.environ.get("LOCATION", "vertex-ai-model-location")}),
                "prompt": ("STRING", {"multiline": True, "default": "A cinematic, aerial shot of a futuristic city with flying cars at sunset."}),
                "storage_uri": ("STRING", {"default": "gs://your-gcs-bucket-path-to-video-output/"}),
            },
            "optional": {
                 "model_id": ("STRING", {"default": "veo-3.0-generate-001"}),
                 "aspect_ratio": (["16:9", "9:16", "1:1", "4:5"],),
                 "duration_seconds": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 16.0, "step": 0.5}),
                 "resolution": (["720p", "1080p"],),
                 "generate_audio": ("BOOLEAN", {"default": True}),
                 "person_generation": (["allow_all", "dont_allow"],),
                 "seed": ("INT", {"default": 1}),
                 "image_base64": ("STRING", {"multiline": False, "default": ""}),
             }
         }
 
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("local_video_path",)
    FUNCTION = "execute"
    CATEGORY = "VertexAI"

    def get_gcloud_token(self):
        """
        Executes 'gcloud auth print-access-token' to get the current bearer token.
        """
        try:
            token = subprocess.check_output(['gcloud', 'auth', 'print-access-token'], text=True).strip()
            return token
        except FileNotFoundError:
            raise Exception("gcloud command not found. Please ensure Google Cloud SDK is installed and in your system's PATH.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.strip() if e.stderr else str(e)
            raise Exception(f"Failed to get gcloud token. Make sure you are authenticated ('gcloud auth login'). Error: {error_message}")

    def download_gcs_file(self, gcs_uri, local_path):
        """Downloads a file from GCS using the gcloud storage cp command."""
        try:
            print(f"Downloading from {gcs_uri} to {local_path}...")
            # Use gcloud to copy the file from the GCS bucket to the local temp path
            result = subprocess.run(['gcloud', 'storage', 'cp', gcs_uri, local_path], check=True, capture_output=True, text=True)
            print("Download successful.")
            return True
        except FileNotFoundError:
            raise Exception("gcloud command not found. Cannot download from GCS.")
        except subprocess.CalledProcessError as e:
            error_message = e.stderr.strip() if e.stderr else str(e)
            print(f"ERROR: Failed to download from GCS. Error: {error_message}")
            raise Exception(f"Failed to download from GCS. See console for details. Error: {error_message}")

    def poll_operation(self, operation_id, gcp_project, gcp_location, model_id, access_token):
        """Polls the long-running operation until it's complete or fails."""
        api_endpoint = f"https://{gcp_location}-aiplatform.googleapis.com/v1/projects/{gcp_project}/locations/{gcp_location}/publishers/google/models/{model_id}:fetchPredictOperation"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {"operationName": operation_id}
        
        timeout_seconds = 900
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                poll_response = requests.post(api_endpoint, headers=headers, json=payload)
                poll_response.raise_for_status()
                status_json = poll_response.json()

                if status_json.get("done", False):
                    print("Operation completed.")
                    if "error" in status_json:
                        error_details = status_json["error"]
                        print(f"ERROR: Operation failed with error: {error_details}")
                        return f"ERROR: Operation failed: {error_details.get('message', 'Unknown error')}"
                    
                    response_data = status_json.get("response", {})
                    videos = response_data.get("videos", [])
                    if videos and isinstance(videos, list):
                        for video in videos:
                            if "gcsUri" in video and video["gcsUri"].startswith("gs://"):
                                print(f"Found video GCS URI: {video['gcsUri']}")
                                return video['gcsUri']
                    
                    print(f"ERROR: Operation finished but no GCS URI found in response: {response_data}")
                    return "ERROR: No GCS URI found. See console for full response."
                else:
                    print("Operation in progress, checking again in 15 seconds...")
                    time.sleep(15)

            except requests.exceptions.HTTPError as e:
                print(f"ERROR: HTTP error while polling: {e}\nResponse: {e.response.text}")
                return "ERROR: HTTP error while polling. See console."
            except Exception as e:
                print(f"ERROR: Unexpected error during polling: {e}")
                return "ERROR: Unexpected error during polling. See console."
        
        print("ERROR: Polling timed out after 15 minutes.")
        return "ERROR: Polling timed out."

    def execute(self, gcp_project, gcp_location, prompt, storage_uri, model_id="veo-3.0-generate-001", aspect_ratio="16:9", duration_seconds=8.0, resolution="720p", generate_audio=True, person_generation="allow_all", seed=1, image_base64=""):
        """
        Prepares, sends the API request, polls for the result, and downloads the video.
        """
        print("Initializing Veo3 Vertex AI video generation.")
        
        try:
            access_token = self.get_gcloud_token()
        except Exception as e:
            print(f"ERROR: {e}")
            return (str(e),)

        api_endpoint = f"https://{gcp_location}-aiplatform.googleapis.com"
        url = f"{api_endpoint}/v1/projects/{gcp_project}/locations/{gcp_location}/publishers/google/models/{model_id}:predictLongRunning"

        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

        instances = [{"prompt": prompt}]
        if image_base64 and image_base64.strip():
            instances[0]["image"] = {"bytesBase64Encoded": image_base64.replace("[\"data:image/png;base64,", "").replace("\"]", ""), "mimeType": "image/png"}

        payload = {"instances": instances, "parameters": {"storageUri": storage_uri, "aspectRatio": aspect_ratio, "sampleCount": 1, "durationSeconds": str(duration_seconds), "personGeneration": person_generation, "seed": seed, "includeRaiReason": True, "generateAudio": generate_audio, "resolution": resolution}}
        
        print(f"Sending request to: {url}\nPayload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()
            operation_id = response_json.get('name')

            if not operation_id:
                print(f"ERROR: Could not find 'name' (operation ID) in API response: {response_json}")
                return ("ERROR: Invalid response format from submission.",)

            print(f"Successfully started job. Operation ID: {operation_id}")
            
            gcs_uri = self.poll_operation(operation_id, gcp_project, gcp_location, model_id, access_token)

            if not gcs_uri or gcs_uri.startswith("ERROR:"):
                return (gcs_uri,)

            try:
                output_dir = folder_paths.get_temp_directory()
                # Create a unique filename based on the GCS path
                filename = os.path.basename(gcs_uri)
                local_video_path = os.path.join(output_dir, filename)
                self.download_gcs_file(gcs_uri, local_video_path)
                return (local_video_path,)
            except Exception as e:
                print(f"ERROR during download: {e}")
                return (str(e),)

        except requests.exceptions.HTTPError as e:
            print(f"ERROR: HTTP error during submission: {e}\nResponse: {e.response.text}")
            return (f"ERROR: HTTP {e.response.status_code} on submission. See console.",)
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during submission: {e}")
            return ("ERROR: Unexpected error on submission. See console.",)

NODE_CLASS_MAPPINGS = {
    "Veo3VertexAINode": Veo3VertexAINode
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Veo3VertexAINode": "Veo3 Video Generator (Vertex AI)"
}

