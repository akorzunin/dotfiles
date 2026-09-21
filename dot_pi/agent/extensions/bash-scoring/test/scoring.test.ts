import assert from "node:assert/strict";
import { test } from "node:test";
import { action, parseDecision, type Decision, type State, type Classifier } from "../core.ts";
import { configFrom, createClassifier, defaults } from "../provider.ts";
import { wrapOperations, type Audit } from "../workflow.ts";
import { createExtension } from "../index.ts";
import type { BashOperations, ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const good: Decision = { category: "test_lint_format", confidence: .99, validationOnly: .99, successful: .99, retryFix: .99 };
const state: State = { command: "pre-commit run --all-files", exitCode: 0, output: "passed", outputTruncated: false, attempt: 0 };
const response = () => ({ model: defaults.model, usage: { input_tokens: 10, output_tokens: 4 }, answers: {
  category: { type: "choice", choice: "test_lint_format", probabilities: { test_lint_format: .99, other: .01 } },
  validationOnly: { type: "noul", noul: .99 }, successful: { type: "noul", noul: .99 }, retryFix: { type: "noul", noul: .99 },
} });
test("strict typed decisions parsing", () => {
  assert.deepEqual(parseDecision(response()), good);
  for (const value of [null, {}, { answers: {} }]) assert.throws(() => parseDecision(value));
  const bad = response(); bad.answers.successful.noul = NaN;
  assert.throws(() => parseDecision(bad));
});
test("only confident successful validation is compressed", () => {
  assert.equal(action(state, good), "ok");
  for (const category of ["read_explore", "build_install_deploy", "other"] as const) assert.equal(action(state, { ...good, category }), "keep");
  for (const patch of [{ confidence: .8 }, { successful: .2 }, { validationOnly: .2 }, { confidence: NaN }]) assert.equal(action(state, { ...good, ...patch }), "keep");
  assert.equal(action({ ...state, outputTruncated: true }, good), "keep");
  assert.equal(action(state, undefined), "keep");
});
test("failure never becomes ok; retries are bounded", () => {
  assert.equal(action({ ...state, exitCode: 1 }, good), "retry");
  for (const exitCode of [null, 130, 137, 143]) assert.equal(action({ ...state, exitCode }, good), "keep");
  assert.equal(action({ ...state, exitCode: 1, attempt: 1 }, good), "keep");
  assert.equal(action({ ...state, exitCode: 1 }, good, .95, false), "keep");
});
async function run(codes: number[], classify: Classifier = async () => good, overrides = {}) {
  let calls = 0, warnings = 0, output = "";
  const audit: Audit = { attempts: [], compress: false };
  const base: BashOperations = { async exec(command, cwd, options) {
    assert.equal(command, state.command); assert.equal(cwd, "/tmp"); assert.equal(options.timeout, 2);
    options.onData(Buffer.from(`attempt ${calls}\n`));
    return { exitCode: codes[calls++] ?? 1 };
  } };
  const ops = wrapOperations(base, classify, { ...defaults, ...overrides }, audit, () => warnings++);
  const result = await ops.exec(state.command, "/tmp", { timeout: 2, onData: data => { output += data.toString(); } });
  return { result, calls, warnings, output, audit };
}
test("retry keeps command, cwd, timeout and both outputs", async () => {
  const r = await run([1, 0]);
  assert.equal(r.calls, 2); assert.equal(r.result.exitCode, 0); assert.equal(r.audit.compress, true);
  assert.match(r.output, /attempt 0/); assert.match(r.output, /rerunning identical/); assert.match(r.output, /attempt 1/);
});
test("retry does not depend on output-compression confidence", async () => {
  const reported: Decision = { category: "test_lint_format", confidence: 1, validationOnly: .37, successful: .04, retryFix: .67 };
  const failed = { ...state, command: "uvx prek run --all-files", exitCode: 1 };
  assert.equal(action(failed, reported, .6), "retry");
  assert.equal(action(failed, { ...reported, confidence: .59 }, .6), "keep");
  assert.equal(action(failed, { ...reported, retryFix: .59 }, .6), "keep");
  assert.equal(action(failed, reported, .6, false), "keep");
  assert.equal(action({ ...failed, attempt: 1 }, reported, .6), "keep");
  assert.equal(action({ ...failed, exitCode: 0 }, { ...reported, successful: 1 }, .6), "keep");
  const r = await run([1, 0], async input => input.attempt === 0 ? reported : good, { threshold: .6 });
  assert.equal(r.calls, 2);
  assert.deepEqual(r.audit.attempts.map(a => a.action), ["retry", "ok"]);
});
test("classifier receives each attempt's output and exit code", async () => {
  const inputs: State[] = [];
  await run([1, 0], async input => { inputs.push(input); return good; });
  assert.deepEqual(inputs.map(({ output, exitCode, attempt }) => ({ output, exitCode, attempt })), [
    { output: "attempt 0\n", exitCode: 1, attempt: 0 },
    { output: "attempt 1\n", exitCode: 0, attempt: 1 },
  ]);
  assert.ok(inputs.every(input => input.command === state.command));
});
test("second failure returns both outputs and does not retry again", async () => {
  const r = await run([1, 1, 0]);
  assert.equal(r.calls, 2); assert.equal(r.audit.compress, false); assert.equal(r.result.exitCode, 1);
  assert.match(r.output, /attempt 0/); assert.match(r.output, /attempt 1/);
});
test("classifier errors and deadlines fail open", async () => {
  for (const classifier of [async () => { throw new Error("offline"); }, () => new Promise<Decision>(() => {})]) {
    const r = await run([1], classifier, { timeoutMs: 10 });
    assert.equal(r.calls, 1); assert.equal(r.warnings, 1); assert.equal(r.audit.compress, false);
    assert.equal(r.output, "attempt 0\n");
  }
});
test("truncated classifier input is not sent or compressed", async () => {
  const r = await run([0], async () => { throw new Error("must not classify"); }, { maxOutputChars: 2 });
  assert.equal(r.warnings, 0); assert.equal(r.audit.compress, false); assert.equal(r.output, "attempt 0\n");
});
test("timeout/spawn errors never lead to retries", async () => {
  let classifications = 0;
  const ops = wrapOperations({ async exec() { throw new Error("timeout:2"); } }, async () => { classifications++; return good; }, defaults, { attempts: [], compress: false }, () => {});
  await assert.rejects(ops.exec("lint", "/tmp", { onData() {} }), /timeout:2/);
  assert.equal(classifications, 0);
});
test("abort during classifier prevents rerun", async () => {
  const controller = new AbortController(); let calls = 0;
  const ops = wrapOperations({ async exec() { calls++; return { exitCode: 1 }; } }, async () => { controller.abort(); return good; }, defaults, { attempts: [], compress: false }, () => {});
  await assert.rejects(ops.exec("lint", "/tmp", { signal: controller.signal, onData() {} }), /aborted/);
  assert.equal(calls, 1);
});
test("config validates limits and providers", () => {
  assert.deepEqual(configFrom({}), defaults);
  for (const c of [{ threshold: NaN }, { debug: "true" }, { autoRetry: "yes" }, { timeoutMs: -1 }, { transport: "compatible" }, { typo: 1 }]) assert.throws(() => configFrom(c));
});
test("OpenRouter SDK uses Decisions endpoint and Pi credentials", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async input => {
    calls++;
    const req = input as Request;
    assert.equal(req.url, "https://openrouter.ai/api/alpha/decisions");
    assert.equal(req.headers.get("authorization"), "Bearer test-only-key");
    const body = await req.json();
    assert.equal(body.model, "typesafe/jev-1.13");
    assert.deepEqual(JSON.parse(body.state), state);
    return Response.json(response());
  };
  try {
    const ctx = { modelRegistry: { async getProviderAuth(provider: string) { assert.equal(provider, "openrouter"); return { auth: { apiKey: "test-only-key" } }; } } } as unknown as ExtensionContext;
    assert.deepEqual(await createClassifier(defaults, ctx)(state), good);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});
test("compatible providers use explicit endpoint and credential; do not leak OpenRouter key", async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async (input, init) => {
    calls++; assert.equal(input, "https://classifier.example/decide");
    assert.equal(new Headers(init?.headers).get("authorization"), "Bearer compatible-key");
    const body = JSON.parse(String(init?.body));
    assert.equal(body.model, "custom/laya");
    assert.deepEqual(JSON.parse(body.state), state);
    return Response.json(response());
  };
  try {
    const ctx = { modelRegistry: { async getProviderAuth() { return { auth: { apiKey: "compatible-key" } }; } } } as unknown as ExtensionContext;
    const config = configFrom({ transport: "compatible", model: "custom/laya", endpoint: "https://classifier.example/decide", authProvider: "laya" });
    assert.deepEqual(await createClassifier(config, ctx)(state), good);
    await assert.rejects(createClassifier({ ...config, authProvider: "openrouter" }, ctx)(state), /separate authProvider/);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});
test("concurrent bash calls keep decisions and outputs isolated", async () => {
  const [passed, failed] = await Promise.all([
    run([0], async () => good),
    run([1], async () => ({ ...good, retryFix: 0 })),
  ]);
  assert.equal(passed.audit.compress, true);
  assert.equal(failed.audit.compress, false);
  assert.equal(passed.calls, 1); assert.equal(failed.calls, 1);
});
test("Pi tool errors preserve both failed attempts", async () => {
  let tool: any; let calls = 0;
  const pi = { registerTool(t: unknown) { tool = t; }, on() {}, registerCommand() {}, registerEntryRenderer() {} } as unknown as ExtensionAPI;
  createExtension({ classifier: async () => good, operations: { async exec(_cmd, _cwd, options) {
    options.onData(Buffer.from(`failure ${++calls}\n`)); return { exitCode: 1 };
  } } })(pi);
  const ctx = { cwd: process.cwd(), hasUI: false, sessionManager: { getSessionId: () => "test", getSessionFile: () => undefined } };
  await assert.rejects(tool.execute("id", { command: "lint" }, undefined, undefined, ctx), (e: Error) => {
    assert.match(e.message, /failure 1/); assert.match(e.message, /failure 2/);
    assert.match(e.message, /Command exited with code 1/); return true;
  });
  assert.equal(calls, 2);
});
test("extension keeps transcript output, compresses model context, preserves modified/error results", async () => {
  let tool: any; const handlers: Record<string, any> = {};
  const pi = { registerTool(t: unknown) { tool = t; }, on(name: string, handler: unknown) { handlers[name] = handler; }, registerCommand() {}, registerEntryRenderer() {} } as unknown as ExtensionAPI;
  createExtension({ classifier: async () => good, operations: { async exec(_cmd, _cwd, options) { options.onData(Buffer.from("All tests passed\n")); return { exitCode: 0 }; } } })(pi);
  const ctx = { cwd: process.cwd(), hasUI: false, sessionManager: { getSessionId: () => "test", getSessionFile: () => undefined } };
  const result = await tool.execute("id", { command: "npm test" }, undefined, undefined, ctx);
  assert.equal(result.content[0].text, "All tests passed\n");
  const message = { role: "toolResult", toolName: "bash", isError: false, ...result };
  assert.equal(handlers.context({ messages: [message] }).messages[0].content[0].text, "ok");
  assert.equal(message.content[0].text, "All tests passed\n");
  for (const changed of [{ ...message, isError: true }, { ...message, content: [{ type: "text", text: "changed by extension" }] }]) {
    assert.deepEqual(handlers.context({ messages: [changed] }).messages[0], changed);
  }
});
