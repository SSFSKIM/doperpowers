// Fail-closed guard for the codex fs sandbox. Observed live (ida-worker-1,
// 2026-08-09): a host that blocks unprivileged userns makes every probe fail
// (`bwrap: loopback: Failed RTM_NEWADDR`), yet codex exits 0 and renders
// findings anyway — 22 consecutive review runs passed as "clean". The
// app-server child's buffered stderr is the machine-emitted trace of that
// state, so its markers turn the run into a hard error instead of a verdict.
// Only that channel is scanned: model-authored channels (final message,
// review text, streamed progress) can quote marker strings innocently.
export const SANDBOX_FAILURE_MARKERS = /RTM_NEWADDR|shell is unavailable|fs sandbox helper failed/;

export function sandboxFailureLines(stderr) {
  if (!stderr) return [];
  return String(stderr).split("\n").filter((line) => SANDBOX_FAILURE_MARKERS.test(line));
}

// Reports every hit through onDiagnostic first (so journaling survives the
// throw), then throws terminally — a blocked sandbox does not heal between
// retries, so a transport retry would spend a full turn to fail identically.
// Under an OUTER codex sandbox (CODEX_SANDBOX set) probe confinement is
// expected and the degraded diff-only render is documented behavior: report
// only, never throw.
export function assertSandboxUsable(label, stderr, { onDiagnostic } = {}) {
  const hits = sandboxFailureLines(stderr);
  if (hits.length === 0) return;
  for (const line of hits) onDiagnostic?.(line);
  if (process.env.CODEX_SANDBOX) return;
  throw Object.assign(
    new Error(
      `fs sandbox unavailable during ${label ?? "codex run"}: ${hits[0].trim()} — ` +
      "findings would be untrustworthy; treat as an engine failure"
    ),
    { terminal: true }
  );
}
