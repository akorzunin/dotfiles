# pi-bash-scoring

Pluggable bash validation optimizer for Pi. Defaults to OpenRouter Decisions,
`typesafe/jev-1.13`, using the official `@openrouter/sdk` and Pi's existing
`openrouter` login via `ctx.modelRegistry.getProviderAuth()`.

## Load

```sh
pi -e ~/.pi/agent/extensions/bash-scoring/
```

(tested against 0.86.1), and Node 22+.

## Behavior

1. Execute the original bash command using Pi's standard backend.
2. Ask typed Decisions questions about its category, whether it is exclusively
   validation, whether it actually succeeded, and whether an already-applied
   auto-fix justifies repeating the **identical** command.
3. Confident successful `test_lint_format` results become `ok` **only in model
   context**. Output and decision scores remain in the UI/session transcript.
4. Confident auto-fix failures rerun once within the same tool execution, using
   the same cwd, environment, timeout, backend, and cancellation signal. No agent
   turn or generated repair command is involved. The second attempt is classified
   again; it can never trigger a third execution.
5. Failures and uncertain results keep their output. Failed retries include both
   attempts with a separator. Pi's standard 2,000-line/50KB truncation and full-log
   spill files still apply; this extension does not remove failed-call output.

Categories: `test_lint_format`, `read_explore`, `build_install_deploy`, `other`.
Commands spanning groups should be `other` and never optimized. Each scoring input
includes the command, combined stdout/stderr, exit code, and attempt number. Success
requires exit code zero **and** classifier confirmation (to catch masked errors).
Signals, timeouts and spawn errors never retry. API errors, invalid responses,
missing credentials and classifier deadlines preserve normal bash behavior.

The classifier is probabilistic, **not a security boundary**. Auto-retry is
classifier-approved as requested, not allowlisted; a misclassification can repeat
side effects. Disable it with `autoRetry: false` when that risk is unacceptable.
Instructions explicitly exclude commits/pushes, installs, deployments and mixed
workflows from validation/retry eligibility.

## Configuration

Optional global `~/.pi/agent/bash-scoring.json` (respects Pi's agent-directory
override). Reload after editing. Project-local configuration is deliberately not
read, so repositories cannot redirect command/output data or credentials.

```json
{
  "enabled": true,
  "debug": false,
  "transport": "openrouter",
  "model": "typesafe/jev-1.13",
  "authProvider": "openrouter",
  "threshold": 0.7,
  "autoRetry": true,
  "timeoutMs": 10000,
  "maxOutputChars": 24000
}
```

`threshold` applies independently to two decisions:
- Compression: category confidence + `validationOnly` + `successful` must pass.
- Retry: category confidence + `retryFix` must pass; `validationOnly` does not gate retries.

Both require the `test_lint_format` category. Exit status and the one-retry limit
still apply. Scores are classifier estimates, not measured accuracy. `/bash-scoring on|off|status` controls the current session. Turning off
also restores original output in subsequent model context requests.

### Debug scores

`/bash-scoring debug` toggles debug output for subsequent bash calls. Use
`/bash-scoring debug on` or `debug off` to set it explicitly; `status` includes
its current state. Set `"debug": true` in `bash-scoring.json` to enable it by
default. Debug defaults to false when omitted. Commands override it for the current
session only; reload/new session restores the configured value without modifying
the file.

Each completed call gets a transcript entry identified by its command and tool-call
ID, showing every attempt's exit code, category, confidence, validation-only,
success and retry-fix probabilities, threshold, and chosen action (`ok`, `keep`,
`retry`). Failed calls are included; missing scores report a skip/failure reason.
Entries are displayed alongside calls in the TUI, retained in session storage,
and **never sent to the model**. Parallel calls are distinguished by tool-call ID.
Debug does not change classification, retries, or output compression. It records
commands but does not duplicate command output or log API credentials/errors.

Switch `model` to any Decisions-compatible model ID available on OpenRouter; no
Jev-specific workflow code exists. For another host implementing the same request
and response contract (including Laya if its endpoint supports that contract):

```json
{
  "transport": "compatible",
  "endpoint": "https://YOUR_HOST/YOUR_DECISIONS_PATH",
  "model": "YOUR_MODEL_ID",
  "apiKeyEnv": "CLASSIFIER_API_KEY"
}
```

Compatible transport uses HTTP JSON, not chat completions. Alternatively set
`authProvider` to a separately configured Pi provider. OpenRouter credentials are
never implicitly forwarded to a different origin. The OpenRouter transport always
uses the official SDK/endpoint; `endpoint` applies only to compatible transport.
No Laya URL or model ID is assumed or bundled.

## Custom adapters and execution backends

Exported `createExtension()` accepts a `classifier`, `operations`, and configuration
(overrides the global JSON). Implement `Classifier` to normalize a different API:

```ts
import { createExtension, type Classifier } from "/absolute/path/to/bash-scoring/index.ts";

const classify: Classifier = async (state, signal) => {
  // Call your classifier with state.command/output/exitCode/attempt and signal.
  return {
    category: "test_lint_format", confidence: 0.99,
    validationOnly: 0.99, successful: 0.99, retryFix: 0.01,
  };
};

export default createExtension({ classifier: classify });
```

The constant scores above illustrate the shape only: do not use them as a real
classifier. `operations` accepts Pi's `BashOperations` for remote/sandbox execution.
Load **one** entry point: disable the default extension when loading a custom
adapter. This extension overrides `bash`; it cannot transparently wrap a separate
extension's bash override. Compose that backend through `operations` instead.
Original Pi `tool_call` gates run before the tool; the internal retry does not emit
another `tool_call`. User `!`/`!!` commands are unaffected.

## Privacy and cost

Commands and combined stdout/stderr are sent to the selected classifier. They may
contain secrets. Credentials themselves are neither logged nor stored by this
extension. Disable optimization for sensitive work or supply a local classifier.

There is one classification request per normally completed eligible-sized bash
attempt, including exploratory calls, plus one if retried. No classification
cache is used because outputs and repository state can change. This adds latency
and classifier cost; savings depend on workload. Classifier usage is currently
not included in Pi's token/cost totals.

Commands or outputs exceeding `maxOutputChars` are **not sent or optimized**;
partial evidence must not hide failures. Raise the limit if needed. Classifier
errors warn once per session in UI mode. No live API requests are made at startup.

## Development

```sh
npm ci
npm test
npm run typecheck
```

Tests use mocked classifiers/backends and mocked HTTP through the real OpenRouter
SDK
