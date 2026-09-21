import type { BashOperations } from "@earendil-works/pi-coding-agent";
import { action, type Classifier, type Decision, type State } from "./core.ts";
import type { Config } from "./provider.ts";

export interface Audit {
  attempts: Array<{ exitCode: number | null; decision?: Decision; action: string; reason?: string }>;
  compress: boolean;
}
export function wrapOperations(base: BashOperations, classify: Classifier, config: Config, audit: Audit, onFailure: () => void): BashOperations {
  return {
    async exec(command, cwd, options) {
      for (let attempt = 0; ; attempt++) {
        let output = "";
        let outputTruncated = false;
        // The real output still streams, unmodified, into Pi's accumulator.
        const result = await base.exec(command, cwd, {
          ...options,
          onData(data) {
            const text = data.toString("utf8");
            if (output.length + text.length > config.maxOutputChars) outputTruncated = true;
            output = (output + text).slice(-config.maxOutputChars);
            options.onData(data);
          },
        });
        if (options.signal?.aborted) throw new Error("aborted");
        const state: State = { command, output, outputTruncated, exitCode: result.exitCode, attempt };
        let decision: Decision | undefined;
        let reason: string | undefined = outputTruncated ? "output exceeds classifier limit"
          : command.length > config.maxOutputChars ? "command exceeds classifier limit" : undefined;
        // Do not send enormous commands or decide based on incomplete output.
        if (!outputTruncated && command.length <= config.maxOutputChars) {
          const controller = new AbortController();
          const signal = AbortSignal.any([controller.signal, ...(options.signal ? [options.signal] : [])]);
          let timer: ReturnType<typeof setTimeout> | undefined;
          let abort: (() => void) | undefined;
          try {
            const deadline = new Promise<never>((_, reject) => {
              abort = () => reject(new Error("Classification cancelled"));
              signal.addEventListener("abort", abort, { once: true });
              timer = setTimeout(() => controller.abort(), config.timeoutMs);
            });
            decision = await Promise.race([classify(state, signal), deadline]);
          } catch {
            reason = "classifier unavailable, invalid response, or deadline exceeded";
            if (!options.signal?.aborted) onFailure();
          } finally {
            clearTimeout(timer);
            if (abort) signal.removeEventListener("abort", abort);
          }
        }
        if (options.signal?.aborted) throw new Error("aborted");
        const next = action(state, decision, config.threshold, config.autoRetry);
        audit.attempts.push({ exitCode: result.exitCode, decision, action: next, reason });
        if (next !== "retry") {
          audit.compress = next === "ok";
          return result;
        }
        options.onData(Buffer.from(`\n[bash-scoring: exit ${result.exitCode}; auto-fix detected, rerunning identical command once]\n`));
      }
    },
  };
}
