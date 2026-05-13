import { app } from "../../../scripts/app.js";

// Ping /vertexai/whoami on page load so the server can capture the
// X-Auth-Request-Email header set by oauth2-proxy and use it as the
// "user" label in Cloud Logging / BigQuery tracking.

let _oauthEmail = null;

app.registerExtension({
    name: "VertexAI.Init",

    async setup() {
        try {
            const resp = await fetch("/vertexai/whoami");
            const data = await resp.json();
            if (data.email) {
                _oauthEmail = data.email;
                console.log(`[VertexAI] Authenticated as ${_oauthEmail}`);
            }
        } catch (e) {
            console.warn("[VertexAI] Could not contact /vertexai/whoami:", e);
        }
    },
});
