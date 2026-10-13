import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { automaticOnly } from "../policy.ts";

function fixture() {
  const tools: string[] = [];
  const commands: string[] = [];
  const hooks: string[] = [];
  const events = {};
  const pi = {
    events,
    registerTool(tool: { name: string }) { tools.push(tool.name); },
    registerCommand(name: string) { commands.push(name); },
    on(name: string) { hooks.push(name); },
  } as unknown as ExtensionAPI;
  return { pi, tools, commands, hooks, events };
}

test("never registers notify_user, including repeated registrations", () => {
  const { pi, tools } = fixture();
  const adapted = automaticOnly(pi);
  for (let i = 0; i < 2; i++) {
    adapted.registerTool({ name: "notify_user" } as any);
  }
  assert.deepEqual(tools, []);
});

test("preserves unrelated tools, settings commands and lifecycle hooks", () => {
  const { pi, tools, commands, hooks, events } = fixture();
  const adapted = automaticOnly(pi);
  adapted.registerTool({ name: "unrelated" } as any);
  adapted.registerCommand("unipi:notify-settings", {} as any);
  adapted.on("session_start", () => {});
  assert.deepEqual(tools, ["unrelated"]);
  assert.deepEqual(commands, ["unipi:notify-settings"]);
  assert.deepEqual(hooks, ["session_start"]);
  assert.equal(adapted.events, events);
  assert.notEqual(adapted, pi);
});

test("does not mutate the host API", () => {
  const { pi, tools } = fixture();
  automaticOnly(pi);
  pi.registerTool({ name: "notify_user" } as any);
  assert.deepEqual(tools, ["notify_user"]);
});

test("package exposes only the adapter and no notification skills", () => {
  const manifest = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.deepEqual(manifest.pi.extensions, ["./index.ts"]);
  assert.deepEqual(manifest.pi.skills, []);
});

test("completion is configured only at the fully settled boundary", () => {
  const config = JSON.parse(readFileSync(new URL("../../../../../dot_unipi/config/notify/config.json", import.meta.url), "utf8"));
  assert.equal(config.events.agent_end.enabled, false);
  assert.equal(config.events.agent_settled.enabled, true);
  assert.equal(config.native.enabled, true);
});
