import { OpenRouter } from "@openrouter/sdk";
import type { ExtensionContext } from "@earendil-works/pi-coding-agent";
import { parseDecision, questions, type Classifier } from "./core.ts";

export interface Config {
  enabled: boolean;
  debug: boolean;
  transport: "openrouter" | "compatible";
  model: string;
  authProvider: string;
  endpoint?: string;
  apiKeyEnv?: string;
  threshold: number;
  autoRetry: boolean;
  timeoutMs: number;
  maxOutputChars: number;
}
export const defaults: Config = {
  enabled: true, debug: false, transport: "openrouter", model: "typesafe/jev-1.13",
  authProvider: "openrouter", threshold: 0.6, autoRetry: true,
  timeoutMs: 10000, maxOutputChars: 24000,
};
export function configFrom(value: unknown): Config {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected config object");
  const c = { ...defaults, ...value } as Config;
  for (const key of Object.keys(value)) if (!(key in defaults) && !["endpoint", "apiKeyEnv"].includes(key)) throw new Error(`Unknown option: ${key}`);
  if (!["openrouter", "compatible"].includes(c.transport) || typeof c.model !== "string" || !c.model || typeof c.authProvider !== "string") throw new Error("Invalid provider config");
  if (![c.enabled, c.autoRetry, c.debug].every(v => typeof v === "boolean")) throw new Error("Invalid boolean config");
  if (!Number.isFinite(c.threshold) || c.threshold < 0.5 || c.threshold > 1) throw new Error("threshold must be 0.5..1");
  for (const n of [c.timeoutMs, c.maxOutputChars]) if (!Number.isInteger(n) || n < 1 || n > 1000000) throw new Error("Invalid limit");
  if (c.apiKeyEnv !== undefined && (typeof c.apiKeyEnv !== "string" || !c.apiKeyEnv)) throw new Error("Invalid apiKeyEnv");
  if (c.transport === "compatible" && !c.endpoint) throw new Error("Compatible transport requires endpoint");
  if (c.endpoint !== undefined) {
    const u = new URL(c.endpoint);
    if (!["http:", "https:"].includes(u.protocol) || u.username || u.password) throw new Error("Invalid endpoint");
  }
  return c;
}
export function createClassifier(config: Config, ctx: ExtensionContext): Classifier {
  return async (state, parentSignal) => {
    const signal = AbortSignal.any([AbortSignal.timeout(config.timeoutMs), ...(parentSignal ? [parentSignal] : [])]);
    signal.throwIfAborted();
    // Never implicitly forward OpenRouter credentials to a different host.
    const key = config.apiKeyEnv ? process.env[config.apiKeyEnv] : (await ctx.modelRegistry.getProviderAuth(config.authProvider))?.auth.apiKey;
    signal.throwIfAborted();
    if (!key) throw new Error("Classifier credentials unavailable");
    const body = { model: config.model, state: JSON.stringify(state), questions };
    if (config.transport === "openrouter") {
      const sdk = new OpenRouter({ apiKey: key });
      return parseDecision(await sdk.alpha.decisions.create({ decisionsRequest: body }, {
        signal, timeoutMs: config.timeoutMs, retries: { strategy: "none" },
      }));
    }
    if (config.authProvider === "openrouter" && !config.apiKeyEnv && new URL(config.endpoint!).origin !== "https://openrouter.ai") {
      throw new Error("Set apiKeyEnv or a separate authProvider for a compatible endpoint");
    }
    const response = await fetch(config.endpoint!, {
      method: "POST", signal, redirect: "error",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`Decisions HTTP ${response.status}`);
    return parseDecision(await response.json());
  };
}
