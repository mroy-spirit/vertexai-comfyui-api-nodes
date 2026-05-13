import { app } from "../../../scripts/app.js";

const SETTINGS = [
    {
        id: "VertexAI.GCPProject",
        name: "GCP Project ID",
        key: "gcp_project",
        widget: "gcp_project",
        tooltip: "Your Google Cloud project ID",
        defaultValue: "",
    },
    {
        id: "VertexAI.GCPLocation",
        name: "GCP Location / Region",
        key: "gcp_location",
        widget: "gcp_location",
        tooltip: "Region (e.g. us-central1) or 'global' for preview models",
        defaultValue: "us-central1",
    },
    {
        id: "VertexAI.StorageURI",
        name: "GCS Storage URI (Veo3)",
        key: "storage_uri",
        widget: "storage_uri",
        tooltip: "GCS output path for Veo3 video generation, e.g. gs://my-bucket/output/",
        defaultValue: "",
    },
    {
        id: "VertexAI.ExtraLabels",
        name: "Extra Labels (JSON)",
        key: "extra_labels",
        widget: null,   // server-side only — not injected into node widgets
        tooltip: 'Additional Cloud Logging labels applied to every node, e.g. {"env":"prod"}',
        defaultValue: "{}",
    },
];

// Cache of current setting values for use in nodeCreated
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
    for (const def of SETTINGS) {
        if (!def.widget) continue;
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

    settings: SETTINGS.map(def => ({
        id: def.id,
        name: def.name,
        category: ["VertexAI", "Google Cloud", def.key],
        type: "text",
        defaultValue: def.defaultValue,
        tooltip: def.tooltip,
        onChange(value) {
            _values[def.id] = value;
            _saveToServer(def.key, value);
        },
    })),

    async setup() {
        // Load persisted values from server and override the settings UI
        try {
            const serverSettings = await fetch("/vertexai/settings").then(r => r.json());
            for (const def of SETTINGS) {
                const serverValue = serverSettings[def.key];
                if (serverValue !== undefined && serverValue !== "") {
                    if (app.ui?.settings?.setSettingValue) {
                        app.ui.settings.setSettingValue(def.id, serverValue);
                    }
                    _values[def.id] = serverValue;
                } else {
                    _values[def.id] = app.ui?.settings?.getSettingValue?.(def.id) ?? def.defaultValue;
                }
            }
        } catch (e) {
            console.warn("[VertexAI] Could not load settings from server:", e);
            for (const def of SETTINGS) {
                _values[def.id] = app.ui?.settings?.getSettingValue?.(def.id) ?? def.defaultValue;
            }
        }
    },

    // Inject into newly dragged nodes only (not workflow-restored ones)
    nodeCreated(node) {
        _injectSettingsIntoNode(node);
    },
});
