import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  // --system-prompt "" falls back to Pi's coding prompt; override the request instead.
  pi.on("before_agent_start", () => ({ systemPrompt: "" }));
}
