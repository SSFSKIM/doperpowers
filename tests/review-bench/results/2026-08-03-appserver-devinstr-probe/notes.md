# App-server native-review developer_instructions transport probe

Question: does `review/start` (app-server path) honor
`developer_instructions` configured on the serving app-server process,
the way `codex exec review -c developer_instructions=...` (CLI path,
proven 2026-07-12 / 2026-07-28) does?

Method: 3-line seeded diff (div-by-zero guard swallowing the error) in a
scratch repo; `with-effort.mjs --effort low -c 'developer_instructions=…
MUST include exactly one extra finding whose title begins with
LENSPROBE-7Q…' -- review --base main --wait`; codex-cli 0.146.0, model
from user config (gpt-5.6-sol).

Result: PASS — probe-out.md contains the LENSPROBE-7Q marker finding AND
the genuine [P1] on the swallowed ZeroDivisionError. Transport works on
the app-server path.

Context: reviewing-prs' bundled engine currently ships scalpels as
`adversarial-review` positional focus (review-engine.sh:106); this probe
re-validates the original devinstr mechanism for the workflow-engine
panel (spec 2026-08-03-codex-workflow-engine-design.md).
