# MessageDisplay's grammar-2 reader. Tags in fenced blocks and inline code
# are literal, using the same strict / balanced glued recovery as the mod.
#
# A flush cannot retract a header. Keep the source and the emitted offset in
# the message's state file: an unmatched inline run waits for its partner or
# paragraph boundary, an incomplete line waits for its end, and a difference
# between strict and glued fences waits for the final reading. Stable text
# (including the body of an open fence) still draws as it arrives.

BEGIN {
  ESC = sprintf("%c", 27)
  DIM = ESC "[2m"; OFF = ESC "[0m"
  # The old to-human, essential, need-input and insight marks draw as
  # messages; a need-input question's <choice> lines stay in its text.
  LABEL["message"] = LABEL["to-human"] = LABEL["essential"] = LABEL["need-input"] = LABEL["insight"] = "message"
  COLOR["message"] = COLOR["to-human"] = COLOR["essential"] = COLOR["need-input"] = COLOR["insight"] = ESC "[1;38;2;215;119;87m"
  MARK = "</?(message|to-human|essential|need-input|insight)>"
  # JavaScript trim's whitespace, as complete UTF-8 alternatives (also works
  # in byte-oriented awk locales). Newline already separates source lines.
  BLANK = "^([ \t\r\013\014]|\302\240|\341\232\200|\342\200\200|\342\200\201|\342\200\202|\342\200\203|\342\200\204|\342\200\205|\342\200\206|\342\200\207|\342\200\210|\342\200\211|\342\200\212|\342\200\250|\342\200\251|\342\200\257|\342\201\237|\343\200\200|\357\273\277)*$"

  if (stack != "") depth = split(stack, open, ",")
  # First three lines are the shell's synchronization / mark state. The rest
  # is the emitted offset, source length, and source (length preserves its
  # trailing newlines). Older three-line state files have no pending source.
  if (previous != "") {
    for (i = 0; i < 3; i++) getline line < previous
    if ((getline line < previous) > 0) {
      emitted = line + 0
      getline size < previous
      while ((getline line < previous) > 0) source = source line "\n"
      source = substr(source, 1, size + 0)
    }
    close(previous)
  }
  previousLength = length(source)
  previousEmitted = emitted + 0
}

# The shell appends X so the last record always exists. Joining line records
# and removing X plus its synthetic newline preserves blank and trailing lines.
{ delta = delta $0 "\n" }

function region(mode, start, end,    n) {
  n = ++count[mode]
  starts[mode, n] = start; ends[mode, n] = end
}

# Linear pairing of equal-length backtick runs, as in MAWS's inlineSpans.
function inlineSpans(mode, start, end, pending,    rest, pos, n, run, last, i, partner) {
  delete runs; delete lengths; delete nextRun; delete latest
  rest = substr(source, start, end - start); pos = start; n = 0
  while (match(rest, /`+/)) {
    run = RLENGTH
    runs[++n] = pos + RSTART - 1; lengths[n] = run
    last = latest[run]
    if (last) nextRun[last] = n
    latest[run] = n
    pos += RSTART + run - 1
    rest = substr(rest, RSTART + run)
  }
  for (i = 1; i <= n; i++) {
    partner = nextRun[i]
    if (partner) {
      region(mode, runs[i], runs[partner] + lengths[partner])
      i = partner
    } else if (pending && (!uncertain[mode] || runs[i] < uncertain[mode])) {
      uncertain[mode] = runs[i]
    }
  }
}

# Fence offsets are relative to the line. Mark tags at its edges are
# transparent only for the glued reading.
function opening(line, mode,    rest, offset, run, info) {
  rest = line; offset = 1
  match(rest, /^[ \t]*/); offset += RLENGTH; rest = substr(rest, RLENGTH + 1)
  if (mode == "glued") {
    while (match(rest, "^" MARK "[ \t]*")) {
      offset += RLENGTH; rest = substr(rest, RLENGTH + 1)
    }
  }
  if (!match(rest, /^(`{3,}|~{3,})/)) return 0
  run = substr(rest, 1, RLENGTH); info = substr(rest, RLENGTH + 1)
  # JavaScript's (.*) fence info excludes CR and Unicode line terminators.
  if (index(info, "\r") || index(info, "\342\200\250") || index(info, "\342\200\251")) return 0
  if (substr(run, 1, 1) == "`" && index(info, "`")) return 0
  fenceChar = substr(run, 1, 1); fenceLength = length(run); fenceStart = offset
  return 1
}

function closing(line, mode, char, size,    rest, offset, run) {
  rest = line
  match(rest, /^[ \t]*/); offset = RLENGTH + 1; rest = substr(rest, offset)
  if (!match(rest, /^(`{3,}|~{3,})/)) return 0
  run = substr(rest, 1, RLENGTH)
  if (substr(run, 1, 1) != char || length(run) < size) return 0
  offset += RLENGTH; rest = substr(rest, RLENGTH + 1)
  match(rest, /^[ \t]*/); offset += RLENGTH; rest = substr(rest, RLENGTH + 1)
  fenceEnd = offset
  if (mode == "glued") {
    while (match(rest, "^" MARK "[ \t]*")) rest = substr(rest, RLENGTH + 1)
  }
  return rest == ""
}

function regionsOf(mode,    at, end, line, char, size, start, para, paraEnd, newline) {
  for (at = 1; at <= length(source) + 1; at = end + 1) {
    newline = index(substr(source, at), "\n")
    end = newline ? at + newline - 1 : length(source) + 1
    line = substr(source, at, end - at)
    if (size) {
      if ((newline || final == "true") && closing(line, mode, char, size)) {
        region(mode, start, at + fenceEnd - 1)
        size = 0
      }
    } else if ((newline || final == "true") && opening(line, mode)) {
      if (para) inlineSpans(mode, para, paraEnd, 0)
      para = 0
      char = fenceChar; size = fenceLength; start = at + fenceStart - 1
    } else if (line ~ BLANK && (newline || final == "true")) {
      if (para) inlineSpans(mode, para, paraEnd, 0)
      para = 0
    } else if (line != "" && (newline || final == "true")) {
      # A partial run may grow on the next flush, so it cannot pair an inline
      # delimiter either. Keep the complete paragraph's unmatched run pending.
      if (!para) para = at
      paraEnd = end
    }
    if (!newline) break
  }
  if (size) region(mode, start, length(source) + 1)
  if (para) inlineSpans(mode, para, paraEnd, final != "true")
}

function insideCode(mode, offset,    low, high, middle) {
  low = 1; high = count[mode]
  while (low <= high) {
    middle = int((low + high) / 2)
    if (offset < starts[mode, middle]) high = middle - 1
    else if (offset >= ends[mode, middle]) low = middle + 1
    else return 1
  }
  return 0
}

function balanced(mode,    rest, offset, tag, kind, n, ok, tags) {
  rest = source; offset = 1; ok = 1
  while (match(rest, MARK)) {
    tag = substr(rest, RSTART, RLENGTH)
    if (!insideCode(mode, offset + RSTART - 1)) {
      if (substr(tag, 2, 1) != "/") tags[++n] = substr(tag, 2, length(tag) - 2)
      else {
        kind = substr(tag, 3, length(tag) - 3)
        if (n && tags[n] == kind) n--
        else { ok = 0; n = 0 }
      }
    }
    offset += RSTART + RLENGTH - 1; rest = substr(rest, RSTART + RLENGTH)
  }
  return ok && !n
}

# Earliest offset where the readings disagree. Before it, either final
# reading will classify every tag identically, regardless of later text.
function difference(    i, a, b) {
  for (i = 1; i <= count["strict"] || i <= count["glued"]; i++) {
    a = starts["strict", i]; b = starts["glued", i]
    if (!a) return b
    if (!b) return a
    if (a != b) return a < b ? a : b
    a = ends["strict", i]; b = ends["glued", i]
    if (a != b) return a < b ? a : b
  }
  return 0
}

function header(kind) { return "\n" COLOR[kind] LABEL[kind] OFF "\n\n" }
function body(text) {
  if (text == "" || depth > 0 || !seen) return text
  return DIM text OFF
}

function draw(line, offset, mode,    out, rest, prefix, at, tag, kind, i, found, step) {
  rest = line
  while (match(rest, MARK)) {
    at = offset + RSTART - 1
    step = RSTART + RLENGTH - 1
    tag = substr(rest, RSTART, RLENGTH)
    prefix = substr(rest, 1, RSTART - 1)
    rest = substr(rest, step + 1); offset += step
    if (insideCode(mode, at)) {
      # Join literal tags with the surrounding text, avoiding SGR codes in
      # the middle of a fence line when this is dimmed working record.
      out = out body(prefix tag)
      continue
    }
    out = out body(prefix)
    if (substr(tag, 2, 1) == "/") {
      kind = substr(tag, 3, length(tag) - 3); found = 0
      for (i = depth; i >= 1; i--) if (open[i] == kind) { found = i; break }
      if (found) {
        depth = found - 1
        if (depth > 0) out = out header(open[depth])
      }
    } else {
      kind = substr(tag, 2, length(tag) - 2)
      seen = 1; open[++depth] = kind; out = out header(kind)
    }
  }
  return out body(rest)
}

END {
  source = source substr(delta, 1, length(delta) - 2)
  regionsOf("strict"); regionsOf("glued")
  mode = "strict"; limit = length(source) + 1
  if (final == "true") {
    if (!balanced("strict") && balanced("glued")) mode = "glued"
  } else {
    # All non-final engine batches end at a line boundary; also support a
    # partial line without guessing whether its last run/tag is complete.
    for (i = length(source); i > 0 && substr(source, i, 1) != "\n"; i--) {}
    limit = i + 1
    if (uncertain["strict"] && uncertain["strict"] < limit) limit = uncertain["strict"]
    if (uncertain["glued"] && uncertain["glued"] < limit) limit = uncertain["glued"]
    at = difference()
    if (at && at < limit) limit = at
  }
  for (at = emitted + 1; at < limit; at = end + 1) {
    rest = substr(source, at, limit - at)
    newline = index(rest, "\n")
    end = newline ? at + newline - 1 : limit
    output = output draw(substr(source, at, end - at), at, mode)
    if (newline) output = output "\n"
  }
  emitted = limit - 1
  # The first line tells the shell whether to replace this flush. Only a
  # fully emitted, unmarked delta with no older buffered text can pass through.
  print (!seen && emitted == length(source) && previousEmitted == previousLength ? 0 : 1)
  printf "%s", output
  if (statefile != "") {
    stack = ""
    for (i = 1; i <= depth; i++) stack = (i == 1 ? open[i] : stack "," open[i])
    printf "%s\n%s\n%s\n%d\n%d\n%s", flush, seen + 0, stack, emitted, length(source), source > statefile
    close(statefile)
  }
}
