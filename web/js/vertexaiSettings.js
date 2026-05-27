import { app } from "../../../scripts/app.js";

// Settings that are injected into per-node widgets when a node is dragged onto
// the canvas. extra_labels and auth-related settings have no per-node widget.
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

// Build a wider editable text input. `onSave(value)` is called on change.
function _editableInput(initialValue, onSave, opts = {}) {
    const el = document.createElement("input");
    el.type = "text";
    el.value = initialValue ?? "";
    el.style.width = "350px";
    if (opts.placeholder) el.placeholder = opts.placeholder;
    el.addEventListener("change", () => onSave(el.value));
    return el;
}

// Build a wider read-only text input (greyed out, not editable).
function _readonlyInput(displayValue) {
    const el = document.createElement("input");
    el.type = "text";
    el.value = displayValue ?? "";
    el.readOnly = true;
    el.style.cssText = "width:350px;opacity:0.5;cursor:default;";
    return el;
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
        const reservedLabels = serverData.reserved_labels ?? {};

        // Editable core settings
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
                tooltip: def.tooltip,
                defaultValue: initialValue,
                type(name, setter, value) {
                    return _editableInput(initialValue, (v) => {
                        _values[def.id] = v;
                        setter(v);
                        _saveToServer(def.key, v);
                    });
                },
                onChange(value) {
                    _values[def.id] = value;
                },
            });
        }

        // Extra Labels — empty by default, with example placeholder
        const rawExtra = serverData.extra_labels ?? "";
        const initialExtra = (rawExtra === "{}" || rawExtra === "") ? "" : rawExtra;
        app.ui.settings.addSetting({
            id: "VertexAI.ExtraLabels",
            name: "Extra Labels (JSON)",
            category: ["VertexAI", "Google Cloud", "extra_labels"],
            tooltip: 'Additional Cloud Logging labels as JSON. Reserved labels (app_id, user_id, project_id) are applied automatically.',
            defaultValue: initialExtra,
            type(name, setter, value) {
                return _editableInput(initialExtra, (v) => {
                    setter(v);
                    _saveToServer("extra_labels", v || "{}");
                }, { placeholder: '{"env": "prod", "team": "ml"}' });
            },
            onChange() {},
        });

        // Auth status — read-only banner
        app.ui.settings.addSetting({
            id: "VertexAI.AuthStatus",
            name: "Authentication Status",
            category: ["VertexAI", "Authentication", "status"],
            tooltip: "Current GCP authentication state. This field is read-only.",
            defaultValue: statusMessage,
            type(name, setter, value) {
                return _readonlyInput(statusMessage);
            },
            onChange() {},
        });

        // Service Account Key Path: off-VM only
        if (!onGce) {
            const initialSaPath = serverData.sa_key_path ?? "";
            app.ui.settings.addSetting({
                id: "VertexAI.SAKeyPath",
                name: "Service Account Key Path",
                category: ["VertexAI", "Authentication", "sa_key_path"],
                tooltip: "Absolute path to a Google Cloud service account JSON key file. Restart ComfyUI after changing.",
                defaultValue: initialSaPath,
                type(name, setter, value) {
                    return _editableInput(initialSaPath, (v) => {
                        setter(v);
                        _saveToServer("sa_key_path", v);
                    });
                },
                onChange() {},
            });
        }

        // Reserved Labels — read-only display, greyed out
        const reservedDefs = [
            { id: "VertexAI.Reserved.AppId",    name: "app_id",     key: "app_id" },
            { id: "VertexAI.Reserved.UserId",    name: "user_id",    key: "user_id" },
            { id: "VertexAI.Reserved.ProjectId", name: "project_id", key: "project_id" },
        ];
        for (const entry of reservedDefs) {
            const val = String(reservedLabels[entry.key] ?? "");
            app.ui.settings.addSetting({
                id: entry.id,
                name: entry.name,
                category: ["VertexAI", "Reserved Labels", entry.name],
                tooltip: "Reserved Cloud Logging label — applied automatically to every request, cannot be edited.",
                defaultValue: val,
                type(name, setter, value) {
                    return _readonlyInput(val);
                },
                onChange() {},
            });
        }
    },

    // Inject server values into newly dragged nodes (not workflow-restored ones)
    nodeCreated(node) {
        _injectSettingsIntoNode(node);
    },
});
