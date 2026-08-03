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

// A line that OPENS like a finding head — optional list marker, then a priority
// tag — but did not parse as one. Anchored at the line start so a body that
// merely mentions "[P2]" mid-sentence is not mistaken for a mangled head.
const ORPHAN_TAG_RE = /^[ \t]*(?:[-*]\s*)?\[P[0-3]\]/;

// The one line that earns a clean verdict. Two sources, one string:
//   - runtime/scripts/lib/render.mjs:263 (`renderReviewResult`, zero findings)
//     emits it verbatim;
//   - the panel's finder sentinel convention — Task 3 instructs each reviewer to
//     end a nothing-found review with exactly this line, because a real clean
//     NATIVE review is free-form prose with no stable phrasing of its own
//     (see fixtures/review-texts/clean-prose-unsentineled.md).
// Deliberately NOT here: "Codex review completed without any stdout output."
// (`renderNativeReviewResult` with empty stdout) — that is a finder that
// produced nothing, which is output loss, not a clean review.
const NO_FINDINGS_LINES = ["No material findings."];

// A finder told to emit one exact line still routinely decorates it — bolds it,
// quotes it, drops the period. Under a raw exact-line test each of those turns a
// genuinely CLEAN review into a failed finder, which the panel reports as an
// interrupted review. So the candidate line is canonicalized first, by a CLOSED
// whitelist: these surrounding wrappers, and one trailing period present or
// absent. Nothing prose-shaped and no substring match — the contract is still
// "the finder said exactly this line", so "No material findings mentioned."
// and "There are no material findings." remain what they are: something else.
const WRAPPERS = [
  ["**", "**"], ["*", "*"], ["`", "`"], ['"', '"'], ["'", "'"],
  ["“", "”"], ["‘", "’"]     // smart double / single quotes
];

function canonicalizeLine(line) {
  let s = line.trim();
  for (let peeled = true; peeled; ) {
    peeled = false;
    for (const [open, close] of WRAPPERS) {
      if (s.length > open.length + close.length && s.startsWith(open) && s.endsWith(close)) {
        s = s.slice(open.length, -close.length).trim();
        peeled = true;
        break;
      }
    }
  }
  return s.endsWith(".") ? s.slice(0, -1) : s;   // exactly ONE period of slack
}

const NO_FINDINGS_CANONICAL = new Set(NO_FINDINGS_LINES.map(canonicalizeLine));

export function extractStubs(reviewText, finderId) {
  const lines = String(reviewText ?? "").split("\n");
  const stubs = [];
  let current = null;
  let orphanTags = 0;

  for (const line of lines) {
    const m = line.match(HEAD_RE);
    if (!m && ORPHAN_TAG_RE.test(line)) orphanTags += 1;
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

  // Partial drift: some heads parsed, at least one tagged line did not. Handing
  // back the parsed subset would silently drop the drifted finding, so the whole
  // finder is suspect — and a suspect finder is a failed one, not a partial
  // success a caller might half-trust. The stubs go with it: `failed` means
  // re-run or escalate this finder, and a re-run recovers them all.
  if (orphanTags > 0) return { stubs: [], clean: false, failed: true };

  if (stubs.length > 0) return { stubs, clean: false, failed: false };

  const clean = lines.some((line) => NO_FINDINGS_CANONICAL.has(canonicalizeLine(line)));
  return { stubs, clean, failed: !clean };
}
