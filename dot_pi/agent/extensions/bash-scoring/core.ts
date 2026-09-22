export const categories = {
  test_lint_format: "Tests, lint, type checks, formatting, validation hooks",
  read_explore: "Read, search, inspect files or system state",
  build_install_deploy: "Build, install dependencies, publish or deploy",
  other: "Mixed groups, unknown purpose, or other actions",
} as const;
export type Category = keyof typeof categories;
export interface State {
  command: string;
  exitCode: number | null;
  output: string;
  outputTruncated: boolean;
  attempt: number;
}
export interface Decision {
  category: Category;
  confidence: number;
  successful: number;
  retryFix: number;
}
export type Classifier = (state: State, signal?: AbortSignal) => Promise<Decision>;
const instruction = `Judge the whole command using command itself, output and exitCode.`;
export const questions = {
  category: {
    type: "choice" as const,
    instructions: instruction + "Choose the purpose of the complete command. uvx prek run --all-files - is lint and format command, its retryable in most cases",
    criteria: {
      test_lint_format: "Only tests, lint, type checks, formatting, or validation hooks; excludes commands used to display or inspect a diff, status, log, file contents, or search results",
      read_explore: "Only read, search, or inspect files or system state, including displaying diffs, status, logs, file contents, or search results",
      build_install_deploy: categories.build_install_deploy,
      other: "Mixed groups (including validation plus inspection output), unknown purpose, or other actions",
    },
  },
  successful: {
    type: "noul" as const,
    instructions: instruction + "Did the command succeed? Output failures override exit zero.",
    criteria: { true: "Exit zero and output shows completed success", false: "Failed, skipped, incomplete, masked failure, or uncertain" },
  },
  retryFix: {
    type: "noul" as const,
    instructions: instruction + "Should this failed validation command be rerun once because it already applied automatic file fixes?",
    criteria: {
      true: "The sole reported failure explicitly says a formatter, linter, or hook modified, fixed, reformatted, or rewrote files; an identical rerun is the normal verification step",
      false: "Any other failure remains; fixes were only suggested, not applied; the command includes commit/push/install/deploy or unrelated side effects; or evidence is uncertain",
    },
  },
};
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid decision response");
  return value as Record<string, unknown>;
}
function probability(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) throw new Error("Invalid probability");
  return value;
}
export function parseDecision(response: unknown): Decision {
  const a = record(record(response).answers);
  const c = record(a.category);
  if (typeof c.choice !== "string" || !Object.hasOwn(categories, c.choice)) throw new Error("Invalid category");
  const p = c.probabilities === undefined ? undefined : record(c.probabilities);
  if (p) for (const value of Object.values(p)) probability(value);
  return {
    category: c.choice as Category,
    confidence: probability(p?.[c.choice] ?? c.confidence),
    successful: probability(record(a.successful).noul),
    retryFix: probability(record(a.retryFix).noul),
  };
}
export function action(state: State, decision: Decision | undefined, threshold = 0.95, retry = true): "keep" | "ok" | "retry" {
  if (!decision || state.outputTruncated || decision.category !== "test_lint_format") return "keep";
  // Validate custom classifier outputs too. NaN must never bypass thresholds.
  if (![decision.confidence, decision.successful, decision.retryFix].every(p => Number.isFinite(p) && p >= 0 && p <= 1)) return "keep";
  if (decision.confidence < threshold) return "keep";
  // Output suppression and retry safety are independent decisions.
  if (state.exitCode === 0) return decision.successful >= threshold ? "ok" : "keep";
  if (retry && state.attempt === 0 && state.exitCode !== null && state.exitCode > 0 && state.exitCode < 128 && decision.retryFix >= threshold) return "retry";
  return "keep";
}
