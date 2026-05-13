import { app } from "../../scripts/app.js";

// Resolved once /vertexai/whoami responds; null if unavailable.
let _oauthEmail = null;
// Nodes created before the fetch finishes are queued here.
let _pendingNodes = [];

function _injectEmail(node, email) {
    const widget = node.widgets?.find(w => w.name === "labels_json");
    if (!widget) return;
    try {
        const labels = JSON.parse(widget.value || "{}");
        labels.app = "comfyui";
        labels.user = email;
        widget.value = JSON.stringify(labels);
    } catch (_) {}
}

app.registerExtension({
    name: "VertexAI.Init",

    async setup() {
        try {
            const resp = await fetch("/vertexai/whoami");
            const data = await resp.json();
            if (data.email) {
                _oauthEmail = data.email;
                console.log(`[VertexAI] Authenticated as ${_oauthEmail}`);
                // Patch any nodes that were already created while the fetch was in flight
                for (const node of _pendingNodes) _injectEmail(node, _oauthEmail);
                _pendingNodes = [];
            }
        } catch (e) {
            console.warn("[VertexAI] Could not contact /vertexai/whoami:", e);
        }
    },

    nodeCreated(node) {
        if (_oauthEmail) {
            _injectEmail(node, _oauthEmail);
        } else {
            // Fetch not done yet — queue for patching once email arrives
            _pendingNodes.push(node);
        }
    },
});
