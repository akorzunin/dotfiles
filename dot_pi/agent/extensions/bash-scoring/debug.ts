import type { Audit } from "./workflow.ts";

export interface DebugEntry {
  toolCallId: string;
  command: string;
  model: string;
  threshold: number;
  enabled: boolean;
  completed: boolean;
  audit: Audit;
  /** Present only for explicit /bash-score runs; normal debug entries do not duplicate tool output. */
  output?: string;
}

export function formatDebug(entry: DebugEntry): string {
  const lines = [
    `[bash-scoring debug] ${JSON.stringify(entry.toolCallId)} $ ${JSON.stringify(entry.command)}`,
    `model=${JSON.stringify(entry.model)} threshold=${entry.threshold}`,
  ];
  if (!entry.enabled) lines.push("scoring skipped: optimizer disabled");
  for (const [index, attempt] of entry.audit.attempts.entries()) {
    const d = attempt.decision;
    const score = (value: number) => Number.isFinite(value) ? value.toFixed(3) : "invalid";
    lines.push(`attempt=${index + 1} exit=${attempt.exitCode ?? "unknown"} action=${attempt.action}`);
    lines.push(d
      ? `category=${JSON.stringify(d.category)} confidence=${score(d.confidence)} successful=${score(d.successful)} retryFix=${score(d.retryFix)}`
      : `scores unavailable: ${attempt.reason ?? "classifier returned no decision"}`);
  }
  if (!entry.completed) lines.push("tool failed or interrupted; original error/output preserved");
  if (entry.enabled && !entry.audit.attempts.length) lines.push("no completed scoring attempt");
  if (entry.output !== undefined) lines.push("", "--- command output ---", entry.output);
  return lines.join("\n");
}
