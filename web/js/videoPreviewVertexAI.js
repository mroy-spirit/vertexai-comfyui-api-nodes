import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

function fitHeight(node) {
    node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
    node?.graph?.setDirtyCanvas(true);
}

function chainCallback(object, property, callback) {
    if (object == undefined) {
        console.error("Tried to add callback to non-existent object");
        return;
    }
    if (property in object) {
        const orig = object[property];
        object[property] = function () {
            const r = orig.apply(this, arguments);
            callback.apply(this, arguments);
            return r;
        };
    } else {
        object[property] = callback;
    }
}

function addPreviewOptions(nodeType) {
    chainCallback(nodeType.prototype, "getExtraMenuOptions", function (_, options) {
        let optNew = [];
        try {
            const previewWidget = this.widgets.find((w) => w.name === "videopreview");
            let url = null;
            if (previewWidget?.videoEl?.hidden === false && previewWidget.videoEl.src) {
                url = previewWidget.videoEl.src;
            }
            if (url) {
                optNew.push(
                    {
                        content: "Open preview",
                        callback: () => window.open(url, "_blank"),
                    },
                    {
                        content: "Save preview",
                        callback: () => {
                            const a = document.createElement("a");
                            a.href = url;
                            a.setAttribute("download", new URLSearchParams(previewWidget.value?.params ?? {}).get("filename") ?? "video.mp4");
                            document.body.append(a);
                            a.click();
                            requestAnimationFrame(() => a.remove());
                        },
                    }
                );
            }
            if (options.length > 0 && options[0] != null && optNew.length > 0) {
                optNew.push(null);
            }
            options.unshift(...optNew);
        } catch (error) {
            console.log(error);
        }
    });
}

function previewVideo(node, videos) {
    const previewNode = node;
    const element = document.createElement("div");

    // Remove existing preview widget if present
    const existing = node.widgets?.findIndex((w) => w.name === "videopreview");
    if (existing >= 0) node.widgets.splice(existing, 1);

    const previewWidget = node.addDOMWidget("videopreview", "preview", element, {
        serialize: false,
        hideOnZoom: false,
        getValue() { return element.value; },
        setValue(v) { element.value = v; },
    });

    previewWidget.videoEls = [];
    previewWidget.value = { hidden: false, paused: false, params: {} };

    previewWidget.computeSize = function (width) {
        let totalHeight = 0;
        for (const videoEl of this.videoEls) {
            if (videoEl.videoWidth && videoEl.videoHeight) {
                totalHeight += (previewNode.size[0] - 20) / (videoEl.videoWidth / videoEl.videoHeight) + 10;
            }
        }
        return totalHeight > 0 ? [width, totalHeight + 10] : [width, -4];
    };

    const container = document.createElement("div");
    container.style.cssText = "width:100%;display:flex;flex-direction:column;gap:10px;";
    element.appendChild(container);
    previewWidget.parentEl = container;

    for (const video of videos) {
        const { filename, subfolder, type } = video;
        const params = { filename, subfolder, type };
        previewWidget.value.params = params;

        const videoEl = document.createElement("video");
        videoEl.controls = true;
        videoEl.loop = false;
        videoEl.muted = false;
        videoEl.style.width = "100%";
        videoEl.src = api.apiURL("/view?" + new URLSearchParams(params));
        videoEl.hidden = false;

        videoEl.addEventListener("loadedmetadata", () => fitHeight(previewNode));
        videoEl.addEventListener("error", () => {
            container.hidden = false;
            fitHeight(previewNode);
        });

        container.appendChild(videoEl);
        previewWidget.videoEls.push(videoEl);
        previewWidget.videoEl = videoEl; // keep reference to last for context menu
    }

    container.hidden = previewWidget.value.hidden;
}

app.registerExtension({
    name: "VideoPreviewVertexAINode",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name === "VideoPreviewVertexAINode") {
            nodeType.prototype.onExecuted = function (data) {
                previewVideo(this, data.videos ?? []);
            };
            addPreviewOptions(nodeType);
        }
    },
});
