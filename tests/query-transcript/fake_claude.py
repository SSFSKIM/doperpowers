#!/usr/bin/env python3
"""A stand-in for `claude -p --resume <copy> ...` (tests only): it logs its
argv, cwd and environment, keeps a copy of the transcript it was asked to
resume, writes the transcript a careless engine might (so cleanup is seen to
run), and answers. Directives in the resumed copy steer it: @@fail exits 1,
@@error reports is_error, @@sleep hangs, @@nothing answers "nothing relevant",
@@empty answers nothing. Otherwise it answers with $STATE/answer.txt."""
import json
import os
import re
import sys
import time

state = os.environ["FAKE_CLAUDE_STATE"]
args = sys.argv[1:]
copy_id = args[args.index("--resume") + 1]
fork_id = args[args.index("--session-id") + 1]
folder = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(os.getcwd())))
with open(os.path.join(folder, copy_id + ".jsonl"), "rb") as f:
    copy = f.read()
os.makedirs(os.path.join(state, "calls"), exist_ok=True)
n = len(os.listdir(os.path.join(state, "calls")))
with open(os.path.join(state, "calls", "%03d-%s.json" % (n, copy_id)), "w") as f:
    json.dump({"args": args, "cwd": os.getcwd(), "folder": folder, "copy": copy.decode(),
               "env": {k: os.environ.get(k) for k in ("SMNS_INTERNAL", "DISABLE_PROMPT_CACHING")}}, f)
# What an engine that persisted anyway would leave: the fork's transcript and its folder.
open(os.path.join(folder, fork_id + ".jsonl"), "w").write("{}\n")
os.makedirs(os.path.join(folder, fork_id, "subagents"), exist_ok=True)

if b"@@sleep" in copy:
    time.sleep(60)
if b"@@fail" in copy:
    sys.stderr.write("API Error: prompt is too long\n")
    sys.exit(1)
result = {"type": "result", "subtype": "success", "is_error": False, "session_id": fork_id,
          "total_cost_usd": 0.0123,
          "usage": {"input_tokens": 2, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 1000,
                    "output_tokens": 50}}
if b"@@error" in copy:
    result.update(is_error=True, subtype="error_during_execution", result="Prompt is too long")
elif b"@@nothing" in copy:
    result["result"] = "Nothing relevant."
elif b"@@empty" in copy:
    result["result"] = ""
else:
    try:
        result["result"] = open(os.path.join(state, "answer.txt")).read()
    except OSError:
        result["result"] = "ok"
print(json.dumps(result))
