import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { createExtension } from "../index.ts";
import { formatDebug, type DebugEntry } from "../debug.ts";
import type { Decision } from "../core.ts";

const scores: Decision = { category: "test_lint_format", confidence: .99, validationOnly: .98, successful: .97, retryFix: .96 };
function harness(codes = [0], classifier = async () => scores) {
  let tool: any, command: any, renderer: any;
  let calls = 0;
  const entries: DebugEntry[] = [], notifications: string[] = [];
  const handlers: Record<string, any> = {};
  const pi = {
    registerTool(value: unknown) { tool = value; },
    registerCommand(_name: string, value: unknown) { command = value; },
    registerEntryRenderer(_name: string, value: unknown) { renderer = value; },
    on(name: string, handler: unknown) { handlers[name] = handler; },
    appendEntry(type: string, data: DebugEntry) { assert.equal(type, "bash-scoring-debug"); entries.push(data); },
  } as unknown as ExtensionAPI;
  createExtension({ classifier, operations: { async exec(_cmd, _cwd, options) {
    options.onData(Buffer.from("original output\n"));
    return { exitCode: codes[calls++] ?? codes.at(-1)! };
  } } })(pi);
  const ctx = { cwd: process.cwd(), hasUI: true,
    ui: { notify(message: string) { notifications.push(message); } },
    sessionManager: { getSessionId: () => "test", getSessionFile: () => undefined },
  };
  return { entries, notifications, handlers,
    start: () => handlers.session_start({}, ctx),
    toggle: (args: string) => command.handler(args, ctx),
    run: (id = "call-id") => tool.execute(id, { command: "npm run lint" }, undefined, undefined, ctx),
    render: (data: DebugEntry) => renderer({ data }).render(80).join("\n"),
  };
}
test("debug toggles, explicit switches, status and default off", async () => {
  const h = harness();
  await h.run(); assert.equal(h.entries.length, 0);
  await h.toggle("debug"); assert.match(h.notifications.at(-1)!, /debug on/);
  const result = await h.run(); assert.equal(h.entries.length, 1);
  assert.equal(result.content[0].text, "original output\n");
  assert.match(h.render(h.entries[0]), /confidence=0.990/);
  const context = h.handlers.context({ messages: [{ role: "toolResult", toolName: "bash", isError: false, ...result }] });
  assert.deepEqual(context.messages[0].content, [{ type: "text", text: "ok" }]);
  await h.toggle("debug off"); await h.run(); assert.equal(h.entries.length, 1);
  await h.toggle("debug on"); await h.toggle("debug on");
  await h.run(); assert.equal(h.entries.length, 2);
  await h.toggle("debug"); await h.toggle("status"); assert.match(h.notifications.at(-1)!, /debug off/);
  await h.toggle("debug invalid"); assert.match(h.notifications.at(-1)!, /Usage:/);
});
test("debug includes both retry attempts even when tool throws", async () => {
  const h = harness([1, 1]); await h.toggle("debug on");
  await assert.rejects(h.run(), /Command exited with code 1/);
  assert.equal(h.entries.length, 1);
  const text = formatDebug(h.entries[0]);
  assert.match(text, /attempt=1 exit=1 action=retry/);
  assert.match(text, /attempt=2 exit=1 action=keep/);
  assert.match(text, /validationOnly=0.980 successful=0.970 retryFix=0.960/);
  assert.match(text, /tool failed or interrupted/);
});
test("debug reports missing scores and disabled optimizer", async () => {
  const h = harness([0], async () => { throw new Error("private API error"); });
  await h.toggle("debug on"); await h.run();
  assert.match(formatDebug(h.entries[0]), /scores unavailable: classifier unavailable/);
  assert.doesNotMatch(formatDebug(h.entries[0]), /private API error/);
  await h.toggle("off"); await h.run();
  assert.match(formatDebug(h.entries[1]), /scoring skipped: optimizer disabled/);
});
test("debug loads from JSON; session toggles do not change disk config", async () => {
  const dir = await mkdtemp(join(tmpdir(), "bash-scoring-config-"));
  const previous = process.env.PI_CODING_AGENT_DIR;
  process.env.PI_CODING_AGENT_DIR = dir;
  try {
    const file = join(dir, "bash-scoring.json");
    await writeFile(file, JSON.stringify({ debug: true }));
    const h = harness();
    await h.start(); await h.run(); assert.equal(h.entries.length, 1);
    await h.toggle("debug off"); await h.run(); assert.equal(h.entries.length, 1);
    await h.start(); await h.run(); assert.equal(h.entries.length, 2);
    await writeFile(file, JSON.stringify({ debug: false }));
    await h.start(); await h.run(); assert.equal(h.entries.length, 2);
    await writeFile(file, JSON.stringify({}));
    await h.toggle("debug on"); await h.start(); await h.run();
    assert.equal(h.entries.length, 2);
  } finally {
    if (previous === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = previous;
    await rm(dir, { recursive: true, force: true });
  }
});
test("parallel debug entries remain associated with their tool call", async () => {
  const h = harness(); await h.toggle("debug on");
  await Promise.all([h.run("first"), h.run("second")]);
  assert.deepEqual(h.entries.map(e => e.toolCallId).sort(), ["first", "second"]);
  for (const entry of h.entries) assert.equal(entry.audit.attempts.length, 1);
});
