// Turn one finder's rendered review text into finding stubs for the verifier.
//
// Calibrated on real renders (tests/codex-companion/fixtures/review-texts/):
// a finding is a list item whose head line carries an optional `[P#]` tag, a
// title, and an em-dash-separated `path:line` or `path:start-end` location;
// its body is the indented continuation up to the next head or a blank line.
//
// The classification is a strict trichotomy — stubs, clean, or failed — and
// zero stubs is never silently ok. A finder that went quiet, drifted out of
// format, or answered in prose is a DEAD finder whose findings are lost; only
// the runtime's own no-findings rendering may be read as a clean verdict.
const HEAD_RE = /^[ \t]*[-*]\s+(?:\[(P[0-3])\]\s*)?(.+?)\s+—\s+(\S+?):(\d+)(?:-(\d+))?\s*$/;

// The one clean rendering the runtime emits, verbatim from
// runtime/scripts/lib/render.mjs (`renderReviewResult`, zero findings).
// Deliberately NOT here: "Codex review completed without any stdout output."
// (`renderNativeReviewResult` with empty stdout) — that is a finder that
// produced nothing, which is output loss, not a clean review.
const NO_FINDINGS_LINES = ["No material findings."];

export function extractStubs(reviewText, finderId) {
  const lines = String(reviewText ?? "").split("\n");
  const stubs = [];
  let current = null;

  for (const line of lines) {
    const m = line.match(HEAD_RE);
    if (m) {
      if (current) stubs.push(current);
      current = {
        id: `${finderId}#${stubs.length + 1}`,
        priority: m[1] ?? "P3",          // an untagged finding is still a finding
        title: m[2].trim(),
        file: m[3],
        lines: m[5] ? `${m[4]}-${m[5]}` : m[4],
        body: ""
      };
    } else if (!line.trim()) {
      if (current) stubs.push(current);
      current = null;
    } else if (current) {
      current.body += (current.body ? "\n" : "") + line.trim();
    }
  }
  if (current) stubs.push(current);

  if (stubs.length > 0) return { stubs, clean: false, failed: false };

  const clean = lines.some((line) => NO_FINDINGS_LINES.includes(line.trim()));
  return { stubs, clean, failed: !clean };
}
