import { app } from "../../../scripts/app.js";

// Settings that are injected into per-node widgets when a node is dragged onto
// the canvas. Each entry maps a ComfyUI setting id to the widget name it should
// populate. extra_labels and auth-related settings have no per-node widget
// and so are absent from this list.
const NODE_WIDGET_SETTINGS = [
    { id: "VertexAI.GCPProject",  key: "gcp_project",  widget: "gcp_project" },
    { id: "VertexAI.GCPLocation", key: "gcp_location", widget: "gcp_location" },
    { id: "VertexAI.StorageURI",  key: "storage_uri",  widget: "storage_uri" },
];

// Cache of current setting values for use in nodeCreated()
const _values = {};

async function _saveToServer(key, value) {
    try {
        await fetch("/vertexai/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [key]: value }),
        });
    } catch (e) {
        console.warn("[VertexAI] Could not save setting to server:", e);
    }
}

function _injectSettingsIntoNode(node) {
    for (const def of NODE_WIDGET_SETTINGS) {
        const value = _values[def.id];
        if (!value) continue;
        const widget = node.widgets?.find(w => w.name === def.widget);
        if (widget) {
            widget.value = value;
            if (widget.inputEl) widget.inputEl.value = value;
        }
    }
}

app.registerExtension({
    name: "VertexAI.Settings",

    async setup() {
        let serverData = {};
        try {
            serverData = await fetch("/vertexai/settings").then(r => r.json());
        } catch (e) {
            console.warn("[VertexAI] Could not load settings from server:", e);
        }
        const authStatus = serverData.auth_status ?? {};
        const onGce = authStatus.on_gce === true;
        const statusMessage = authStatus.message ?? "Authentication status unknown.";

        // The four core settings, registered in both environments.
        const coreDefs = [
            {
                id: "VertexAI.GCPProject",
                name: "GCP Project ID",
                key: "gcp_project",
                category: ["VertexAI", "Google Cloud", "gcp_project"],
                tooltip: "Your Google Cloud project ID. Auto-detected from the GCE metadata server when running on a VM.",
                defaultValue: "",
            },
            {
                id: "VertexAI.GCPLocation",
                name: "GCP Location / Region",
                key: "gcp_location",
                category: ["VertexAI", "Google Cloud", "gcp_location"],
                tooltip: "Region (e.g. us-central1) or 'global' for preview models.",
                defaultValue: "us-central1",
            },
            {
                id: "VertexAI.StorageURI",
                name: "GCS Storage URI (Veo3)",
                key: "storage_uri",
                category: ["VertexAI", "Google Cloud", "storage_uri"],
                tooltip: "GCS output path for Veo3 video generation, e.g. gs://my-bucket/output/",
                defaultValue: "",
            },
            {
                id: "VertexAI.ExtraLabels",
                name: "Extra Labels (JSON)",
                key: "extra_labels",
                category: ["VertexAI", "Google Cloud", "extra_labels"],
                tooltip: 'Cloud Logging labels applied to every node. Pre-filled with app=comfyui and user=<your OAuth email>; you can add your own, e.g. {"app":"comfyui","user":"you@example.com","env":"prod"}',
                defaultValue: "{}",
            },
        ];

        for (const def of coreDefs) {
            const serverValue = serverData[def.key];
            const initialValue = (serverValue !== undefined && serverValue !== "")
                ? serverValue
                : def.defaultValue;
            _values[def.id] = initialValue;
            app.ui.settings.addSetting({
                id: def.id,
                name: def.name,
                category: def.category,
                type: "text",
                defaultValue: initialValue,
                tooltip: def.tooltip,
                onChange(value) {
                    _values[def.id] = value;
                    _saveToServer(def.key, value);
                },
            });
        }

        // Read-only auth status banner. Registered in both environments.
        // The onChange handler reverts any user edit so the displayed value
        // always matches the server-reported status.
        app.ui.settings.addSetting({
            id: "VertexAI.AuthStatus",
            name: "Authentication Status",
            category: ["VertexAI", "Authentication", "status"],
            type: "text",
            defaultValue: statusMessage,
            tooltip: "Current GCP authentication state. This field is read-only; any edits are reverted.",
            onChange(value) {
                if (value !== statusMessage && app.ui?.settings?.setSettingValue) {
                    app.ui.settings.setSettingValue("VertexAI.AuthStatus", statusMessage);
                }
            },
        });

        // Service Account Key Path: off-VM only. On GCE the metadata server
        // handles auth, so this field is not registered at all.
        if (!onGce) {
            app.ui.settings.addSetting({
                id: "VertexAI.SAKeyPath",
                name: "Service Account Key Path",
                category: ["VertexAI", "Authentication", "sa_key_path"],
                type: "text",
                defaultValue: serverData.sa_key_path ?? "",
                tooltip: "Absolute path to a Google Cloud service account JSON key file. Restart ComfyUI after changing for the new credentials to fully take effect.",
                onChange(value) {
                    _saveToServer("sa_key_path", value);
                },
            });
        }
    },

    // Inject into newly dragged nodes only (not workflow-restored ones)
    nodeCreated(node) {
        _injectSettingsIntoNode(node);
    },
});
