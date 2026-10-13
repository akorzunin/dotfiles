import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import notify from "@pi-unipi/notify";
import { automaticOnly } from "./policy.ts";

export default function (pi: ExtensionAPI) {
  notify(automaticOnly(pi));
}
