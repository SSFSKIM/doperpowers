# Redraws one flush of a streaming assistant message for the `to-human`
# output style: each mark becomes a header line and the working record
# between marks dims, so the report reads as it arrives.
#
# Reads the flush on stdin, writes the replacement on stdout. `seen` says
# whether the message has marked anything before this flush and `stack`
# carries the marks left open by the previous flush, innermost last, as a
# comma-separated list; at the end this flush records its index (`flush`) and both
# in `statefile`, unless that is empty (the message's last flush).
#
# Nothing is dimmed until the message's first mark: a message that never
# marks anything (every session that does not use the output style) passes
# through unchanged.

BEGIN {
  ESC = sprintf("%c", 27)
  DIM = ESC "[2m"
  OFF = ESC "[0m"
  LABEL["to-human"] = "to human";    COLOR["to-human"] = ESC "[1;36m"
  LABEL["essential"] = "essential";  COLOR["essential"] = ESC "[1;33m"
  LABEL["need-input"] = "need input"; COLOR["need-input"] = ESC "[1;35m"
  CHOICE = "\342\227\207 "       # ◇ U+25C7, the marker of a choice
  RECOMMENDED = "\342\227\206 "  # ◆ U+25C6, the marker of the recommended one

  depth = 0
  if (stack != "") {
    depth = split(stack, open, ",")
  }
}

function header(kind) {
  return "\n" COLOR[kind] LABEL[kind] OFF "\n\n"
}

# Text between two marks: the mark's own body, or the working record.
function body(text) {
  if (text == "") return ""
  if (depth > 0) return text
  if (seen) return DIM text OFF
  return text
}

{
  rest = $0
  out = ""

  while (match(rest, /<\/?(to-human|essential|need-input|choice( recommended)?)>/)) {
    out = out body(substr(rest, 1, RSTART - 1))
    tag = substr(rest, RSTART, RLENGTH)
    rest = substr(rest, RSTART + RLENGTH)

    if (tag ~ /^<\/?choice/) {
      # A choice under a need-input mark draws as a line under its marker,
      # the recommended one under the filled marker; anywhere else the tag
      # is text, as the module reads it.
      if (depth > 0 && open[depth] == "need-input") {
        # Each choice on a line of its own, wherever the model put the tag.
        if (tag != "</choice>" && out != "") out = out "\n"
        if (tag == "<choice>") out = out CHOICE
        else if (tag == "<choice recommended>") out = out RECOMMENDED
      } else {
        out = out body(tag)
      }
      continue
    }

    if (substr(tag, 2, 1) == "/") {
      kind = substr(tag, 3, length(tag) - 3)
      at = 0
      for (i = depth; i >= 1; i--) {
        if (open[i] == kind) { at = i; break }
      }
      if (at > 0) {
        depth = at - 1
        # The enclosing mark resumes: its header opens the run again.
        if (depth > 0) out = out header(open[depth])
      }
    } else {
      kind = substr(tag, 2, length(tag) - 2)
      seen = 1
      open[++depth] = kind
      out = out header(kind)
    }
  }

  print out body(rest)
}

END {
  if (statefile == "") exit
  line = ""
  for (i = 1; i <= depth; i++) {
    line = (i == 1 ? open[i] : line "," open[i])
  }
  print flush "\n" seen "\n" line > statefile
  close(statefile)
}
