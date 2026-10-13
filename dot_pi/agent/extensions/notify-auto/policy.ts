import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Preserve upstream commands and lifecycle hooks, but never register its agent tool. */
export function automaticOnly(pi: ExtensionAPI): ExtensionAPI {
  return {
    ...pi,
    registerTool(tool) {
      if (tool.name !== "notify_user") pi.registerTool(tool);
    },
  };
}
