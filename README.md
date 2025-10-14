# ComfyUI Custom Nodes for Google Vertex AI

This repository contains ComfyUI custom nodes that allow you to leverage the power of Google's Vertex AI models, specifically Veo3 for video generation and Imagen4 for image generation, directly within your ComfyUI workflows.

## Features

*   **Veo3 Node:** Generate high-quality videos from text prompts using Google's state-of-the-art Veo3 model.
*   **Imagen4 Node:** Create stunning images from text prompts with Google's powerful Imagen4 model.

## Prerequisites

Before you can use these custom nodes, you need to have the Google Cloud SDK installed and authenticated on your system.

### 1. Install Google Cloud SDK

Follow the official Google Cloud documentation to install the `gcloud` CLI tool for your operating system:

[https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install)

### 2. Authenticate with Google Cloud

After installing the SDK, you need to authenticate your machine. Run the following command in your terminal:

```bash
gcloud auth application-default login
```

This command will open a web browser where you can log in with your Google account and grant the necessary permissions.

## Installation

To install these custom nodes, you need to clone this repository into the `custom_nodes` directory of your ComfyUI installation.

1.  Navigate to your ComfyUI installation directory.
2.  Go to the `custom_nodes` directory.
3.  Clone this repository:

    ```bash
    git clone https://github.com/your-username/vertexai-comfyui-api-nodes.git
    ```

4.  Install the required Python packages for each custom node. Navigate to the directory of each node and run:

    ```bash
    pip install -r requirements.txt
    ```

    For example:

    ```bash
    cd vertexai-comfyui-api-nodes/Veo3Custom
    pip install -r requirements.txt
    cd ../Imagen4Custom
    pip install -r requirements.txt
    ```

5.  Restart ComfyUI.

## Usage

Once installed, you will find the new nodes in the "Vertex AI" category in ComfyUI.

*   **Veo3 Node:** This node takes a text prompt as input and generates a video. You can use the [VHS (Video Helper Suite)](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) for video manipulation and previewing.
*   **Imagen4 Node:** This node takes a text prompt as input and generates an image. You can use the [Easy API Nodes](https://github.com/lldacing/comfyui-easyapi-nodes/) for image manipulation and previewing.

## Preview

![Comfy UI Preview](https://raw.githubusercontent.com/NucleusEngineering/vertexai-comfyui-api-nodes/refs/heads/main/static/sample.png)


## License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.