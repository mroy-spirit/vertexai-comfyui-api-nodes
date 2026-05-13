import { app } from "../../scripts/app.js";

let _oauthEmail = null;
let _pendingNodes = [];

function _injectEmail(node, email) {
    const widget = node.widgets?.find(w => w.name === "labels_json");
    if (!widget) return;
    try {
        const labels = JSON.parse(widget.value || "{}");
        labels.app = "comfyui";
        labels.user = email;
        const newValue = JSON.stringify(labels);
        widget.value = newValue;
        // Update the DOM element if the widget is currently rendered as an input
        if (widget.inputEl) widget.inputEl.value = newValue;
        node.setDirtyCanvas?.(true, true);
    } catch (_) {}
}

function _onEmailResolved(email) {
    _oauthEmail = email;
    console.log(`[VertexAI] Authenticated as ${email}`);
    // Patch queued nodes (created before fetch completed)
    for (const node of _pendingNodes) _injectEmail(node, email);
    _pendingNodes = [];
    // Patch all nodes already on the canvas (loaded workflow, etc.)
    for (const node of (app.graph?._nodes ?? [])) _injectEmail(node, email);
}

app.registerExtension({
    name: "VertexAI.Init",

    async setup() {
        try {
            const resp = await fetch("/vertexai/whoami");
            const data = await resp.json();
            if (data.email) _onEmailResolved(data.email);
        } catch (e) {
            console.warn("[VertexAI] Could not contact /vertexai/whoami:", e);
        }
    },

    // Newly dragged node
    nodeCreated(node) {
        if (_oauthEmail) _injectEmail(node, _oauthEmail);
        else _pendingNodes.push(node);
    },

    // Node restored from a saved workflow
    loadedGraphNode(node) {
        if (_oauthEmail) _injectEmail(node, _oauthEmail);
        else _pendingNodes.push(node);
    },
});
