import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import {
  createBashToolDefinition, createLocalBashOperations, getAgentDir,
  type BashOperations, type ExtensionAPI,
} from "@earendil-works/pi-coding-agent";
import { Text } from "@earendil-works/pi-tui";
import { formatDebug, type DebugEntry } from "./debug.ts";
import type { Classifier } from "./core.ts";
import { configFrom, createClassifier, defaults, type Config } from "./provider.ts";
import { wrapOperations, type Audit } from "./workflow.ts";

export type { Classifier, Decision, State } from "./core.ts";
export type { Config } from "./provider.ts";
export interface PluginOptions {
  config?: Partial<Config>;
  classifier?: Classifier;
  operations?: BashOperations;
}
const digest = (content: unknown) => createHash("sha256").update(JSON.stringify(content)).digest("hex");

/** Supply a classifier and/or remote/sandbox operations to compose with other tools. */
export function createExtension(options: PluginOptions = {}) {
  return (pi: ExtensionAPI) => {
    let config = configFrom(options.config ?? {});
    let warned = false;
    pi.registerEntryRenderer("bash-scoring-debug", entry =>
      new Text(formatDebug(entry.data as DebugEntry), 0, 0));
    pi.on("session_start", async (_event, ctx) => {
      warned = false;
      try {
        const file = join(getAgentDir(), "bash-scoring.json");
        let disk: unknown = {};
        try { disk = JSON.parse(await readFile(file, "utf8")); }
        catch (e) { if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw e; }
        config = configFrom({ ...configFrom(disk), ...options.config });
      } catch {
        config = { ...defaults, enabled: false };
        if (ctx.hasUI) ctx.ui.notify("bash-scoring: invalid config; optimization disabled", "warning");
      }
    });
    const definition = createBashToolDefinition(process.cwd());
    pi.registerTool({
      ...definition,
      description: definition.description + " Successful validation output may be reduced to ok in model context. Auto-fixing validation commands may be repeated once.",
      async execute(id, params, signal, onUpdate, ctx) {
        const current = { ...config };
        const debugCall = current.debug;
        const audit: Audit = { attempts: [], compress: false };
        const base = options.operations ?? createLocalBashOperations();
        const operations = current.enabled ? wrapOperations(base, options.classifier ?? createClassifier(current, ctx), current, audit, () => {
          if (!warned && ctx.hasUI) {
            warned = true;
            ctx.ui.notify("bash-scoring: classifier unavailable/invalid; keeping normal output", "warning");
          }
        }) : base;
        const tool = createBashToolDefinition(ctx.cwd, { operations });
        // Pi owns streaming, environment injection, cancellation, errors and output spill files.
        let completed = false;
        try {
          const result = await tool.execute(id, params, signal, onUpdate, ctx);
          completed = true;
          return {
            ...result,
            details: {
              ...result.details,
              bashScoring: { ...audit, version: 1, contentHash: digest(result.content) },
            },
          };
        } finally {
          if (debugCall) {
            // Custom entries are rendered alongside the call, never sent to the model.
            // Record failures too: Pi's execute errors otherwise discard result details.
            try {
              pi.appendEntry<DebugEntry>("bash-scoring-debug", {
                toolCallId: id, command: params.command, model: options.classifier ? "custom adapter" : current.model,
                threshold: current.threshold, enabled: current.enabled, completed, audit,
              });
            } catch { /* Debug persistence must not change a command's outcome. */ }
          }
        }
      },
    });
    // Non-destructive: UI and transcript retain output. Details survive reload/fork.
    pi.on("context", event => ({
      messages: event.messages.map(message => {
        if (!config.enabled || message.role !== "toolResult" || message.toolName !== "bash" || message.isError) return message;
        const marker = (message.details as { bashScoring?: { version?: number; compress?: boolean; contentHash?: string } } | undefined)?.bashScoring;
        if (marker?.version !== 1 || marker.compress !== true || marker.contentHash !== digest(message.content)) return message;
        return { ...message, content: [{ type: "text" as const, text: "ok" }] };
      }),
    }));
    pi.registerCommand("bash-score", {
      description: "Run a bash command and show its scoring decision",
      handler: async (args, ctx) => {
        const command = args.trim();
        if (!command) {
          ctx.ui.notify("Usage: /bash-score <command>", "warning");
          return;
        }
        const current = { ...config };
        const audit: Audit = { attempts: [], compress: false };
        const base = options.operations ?? createLocalBashOperations();
        const operations = wrapOperations(
          base,
          options.classifier ?? createClassifier(current, ctx),
          current,
          audit,
          () => {},
        );
        const tool = createBashToolDefinition(ctx.cwd, { operations });
        let output = "(no output)";
        let completed = false;
        try {
          const result = await tool.execute(
            `bash-score-${Date.now()}`,
            { command },
            ctx.signal,
            update => {
              output = update.content.map(part => part.type === "text" ? part.text : "").join("") || output;
            },
            ctx,
          );
          output = result.content.map(part => part.type === "text" ? part.text : "").join("") || output;
          completed = true;
        } catch (error) {
          output = error instanceof Error ? error.message : String(error);
        }
        pi.appendEntry<DebugEntry>("bash-scoring-debug", {
          toolCallId: "manual", command,
          model: options.classifier ? "custom adapter" : current.model,
          threshold: current.threshold, enabled: true, completed, audit, output,
        });
      },
    });
    pi.registerCommand("bash-scoring", {
      description: "Validation output optimizer: on, off, status, debug [on|off]",
      getArgumentCompletions: prefix => ["on", "off", "status", "debug", "debug on", "debug off"]
        .filter(value => value.startsWith(prefix)).map(value => ({ value, label: value })),
      handler: async (args, ctx) => {
        const command = args.trim().replace(/\s+/g, " ");
        if (command === "on") config.enabled = true;
        else if (command === "off") config.enabled = false;
        else if (command === "debug") config.debug = !config.debug;
        else if (command === "debug on") config.debug = true;
        else if (command === "debug off") config.debug = false;
        else if (command && command !== "status") {
          ctx.ui.notify("Usage: /bash-scoring on|off|status|debug [on|off]", "warning");
          return;
        }
        ctx.ui.notify(`bash-scoring: ${config.enabled ? "on" : "off"}; ${config.model}; threshold ${config.threshold}; retry ${config.autoRetry ? "once" : "off"}; debug ${config.debug ? "on" : "off"}`, "info");
      },
    });
  };
}
export default createExtension();
