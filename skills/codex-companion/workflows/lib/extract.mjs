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

// The path is `.+?` rather than `\S+?`: a valid repository path may contain
// spaces, and a head whose only sin was a spaced path used to fall through to
// the body of the previous finding — silently merging two findings into one.
// The TITLE is greedy so the separator binds to the LAST em-dash on the line,
// which is what makes a title that itself contains an em-dash parse correctly.
const HEAD_RE = /^[ \t]*[-*]\s+(?:\[(P[0-3])\]\s*)?(.+)\s+—\s+(.+?):(\d+)(?:-(\d+))?\s*$/;

// A line that OPENS like a finding head but did not parse as one. Two shapes
// count, and the second is the one that matters most:
//   - an explicit `[P#]` tag: a mangled tagged head. Anchored at the line start
//     so a body that merely mentions "[P2]" mid-sentence is not mistaken for one.
//   - the full head SHAPE with no tag at all — list marker, em-dash separator,
//     `:NN` location tail. An UNTAGGED head that fails HEAD_RE looks exactly
//     like this, and counting only tagged ones let a real finding be absorbed
//     into the previous finding's body while the extractor reported success.
const ORPHAN_TAG_RE = /^[ \t]*(?:[-*]\s*)?\[P[0-3]\]/;
const HEAD_SHAPE_RE = /^[ \t]*[-*]\s+.*\s—\s.*:\d+(?:-\d+)?\s*$/;

// The third shape, and the one that closed the last hole: ANY top-level list
// item that did not parse as a head. A finder's findings are its list items, so
// a bullet in neither of the shapes above — no tag, no location, just prose —
// is a finding whose head drifted past recognition, and it used to be absorbed
// into the previous item's body. Beside the clean marker that made a lane with
// a defect in it read CLEAN. Top level only (column 0): an INDENTED bullet is a
// body listing its own points, which every render is entitled to write.
const TOP_LEVEL_ITEM_RE = /^[-*]\s+\S/;

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

// The clean verdict a native finder can actually give. A review turn renders
// reviewText from codex's own review pipeline, so "end your final message with
// this line" never reaches it — live-proven twice, in
// tests/review-bench/results/2026-08-03-native-clean-render-probe/notes.md: the
// clean render came back as free-form prose both without the instruction and
// with it. The SAME developer_instructions channel does reliably shape FINDINGS
// (LENSPROBE-7Q, .../2026-08-03-appserver-devinstr-probe/), so the panel asks a
// finder that found nothing for one marker finding instead, and this is its
// title. Same closed-whitelist normalization as the line sentinel, plus case.
const MARKER_TITLE = "NO-MATERIAL-FINDINGS";
const isMarkerTitle = (title) => canonicalizeLine(title).toUpperCase() === MARKER_TITLE;

export function extractStubs(reviewText, finderId) {
  const lines = String(reviewText ?? "").split("\n");
  const stubs = [];
  let current = null;
  let malformedHeads = 0;

  for (const line of lines) {
    const m = line.match(HEAD_RE);
    if (!m && (ORPHAN_TAG_RE.test(line) || HEAD_SHAPE_RE.test(line) || TOP_LEVEL_ITEM_RE.test(line))) malformedHeads += 1;
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

  // Partial drift: some heads parsed, at least one head-shaped line did not. Handing
  // back the parsed subset would silently drop the drifted finding, so the whole
  // finder is suspect — and a suspect finder is a failed one, not a partial
  // success a caller might half-trust. The stubs go with it: `failed` means
  // re-run or escalate this finder, and a re-run recovers them all.
  if (malformedHeads > 0) return { stubs: [], clean: false, failed: true };

  if (stubs.length > 0) {
    const real = stubs.filter((s) => !isMarkerTitle(s.title));
    // The marker ALONE is the clean verdict, and it carries no stub: it stands
    // for "nothing found", not for something the verifier should judge. ALONE is
    // literal — the instruction says exactly one marker, and a finder that filed
    // it twice did not follow the instruction it was given, so nothing in that
    // render says what it actually meant. A lane like that is failed, not clean:
    // the clean verdict is the one answer this extractor may never guess at.
    if (real.length === 0) {
      return stubs.length === 1
        ? { stubs: [], clean: true, failed: false }
        : { stubs: [], clean: false, failed: true };
    }
    // The marker BESIDE real findings is a finder that misread "if and only if".
    // Losing real findings to a stray marker would be the worst outcome, so the
    // marker is dropped and the findings kept. Ids stay as parsed — they are
    // opaque keys, and the gap is the truth about the render. `clean` still
    // demands the marker stood alone, so this can never fake a clean verdict.
    return { stubs: real, clean: false, failed: false };
  }

  // The structured renderer's own clean line (render.mjs) still counts: that
  // path does emit it verbatim, and it costs nothing to keep recognizing.
  const clean = lines.some((line) => NO_FINDINGS_CANONICAL.has(canonicalizeLine(line)));
  return { stubs, clean, failed: !clean };
}
