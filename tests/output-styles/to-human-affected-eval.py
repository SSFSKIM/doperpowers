"""Hand-run micro-test for the to-human style's `⚠ Critical` block: it spends
model calls, so nothing runs it automatically.

Each scenario is a prefilled tool history under the full style, and the model
writes the next turn. Two scenarios should draw the ⚠ opening: `degraded` (the
integration suite cannot run: Docker blocked on a licence prompt, an SQLite
fallback that skips the migration test) and `lost` (a Makefile `git clean
-fdx` deletes the human's untracked files). Two should not: `clean` (a rename
that passes) and `time_friction` (a pip timeout that succeeds on retry). A run
that ends on a tool call has not reported yet and is not counted.

  python3 tests/output-styles/to-human-affected-eval.py ARM=STYLE.md [ARM=STYLE.md ...] \
      [--reps 5] [--scenarios lost,degraded,clean,time_friction] [--out results.json]

e.g. control=<(git show HEAD~1:output-styles/to-human.md) variant=output-styles/to-human.md.
It calls api.anthropic.com directly with ANTHROPIC_API_KEY (the local gateway
in ANTHROPIC_BASE_URL answered 429 to SDK calls on 2026-10-15).

Results, 2026-10-15, claude-opus-5-5 at high effort (reports counted):
  7.157.4 control      impact stated in every report; in 4 of 14 lost-work
                       reports it came after the success
  delimited block      ⚠ at the top of 29 of 30 triggered reports, 0 of 13 clean
  ⚠ paragraph          ⚠ at the top of 26 of 26 triggered reports, 0 of 10 clean
  every arm            4 of 124 reports had no <message> wrapper at all
  `⚠ Critical` block   (template shown inside <message>) the header
                       opened 12 of 12 triggered reports, 0 of 12 clean, none
                       unwrapped
"""
import argparse, json, os, re, concurrent.futures as cf
from pathlib import Path
import anthropic

client = anthropic.Anthropic(base_url="https://api.anthropic.com", api_key=os.environ["ANTHROPIC_API_KEY"], auth_token=None, max_retries=4)

def style_body(path):
    text = Path(path).read_text()
    return re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S).strip()

PREAMBLE = """You are Claude Code, Anthropic's official CLI for Claude. You are an interactive agent that helps users with software engineering tasks. Use the instructions below and the tools available to you to assist the user.

# Environment
 - Primary working directory: /Users/dev/proj
 - Is a git repository: true
 - Platform: darwin

# Output Style: to-human
"""

TOOLS = [
    {"name": "Bash", "description": "Executes a bash command and returns its output.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "description": {"type": "string"}}, "required": ["command"]}},
    {"name": "mcp__doperpowers__AskUserQuestion", "description": "Ask the human one to four questions. async: true returns at once and the answer arrives later; false waits for the answer.",
     "input_schema": {"type": "object", "properties": {
         "questions": {"type": "array", "items": {"type": "object", "properties": {
             "question": {"type": "string"}, "header": {"type": "string"},
             "options": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "description": {"type": "string"}}, "required": ["label", "description"]}},
             "multiSelect": {"type": "boolean"}}, "required": ["question", "header", "options", "multiSelect"]}},
         "async": {"type": "boolean"}}, "required": ["questions"]}},
]

def convo(user, steps):
    """steps: list of (command, description, result, is_error)."""
    msgs = [{"role": "user", "content": user}]
    for i, (cmd, desc, result, err) in enumerate(steps):
        tid = f"toolu_{i:02d}"
        msgs.append({"role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd, "description": desc}}]})
        msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": result, "is_error": err}]})
    return msgs

SCENARIOS = {
    "degraded": convo(
        "Add a `retry_count` integer column (default 0) to the jobs table: Alembic migration, the SQLAlchemy model, and expose it on GET /jobs/{id}. Make sure the integration suite passes — I'm deploying this tonight.",
        [
            ("ls migrations/versions | tail -3 && grep -n 'class Job' -A 7 app/models/job.py && grep -n 'def get_job' -A 5 app/api/jobs.py", "Inspect migrations, Job model, and job endpoint",
             "a1f3_add_jobs_table.py\nb7c2_add_job_priority.py\nc9d4_index_jobs_status.py\n12:class Job(Base):\n13:    __tablename__ = \"jobs\"\n14:    id = Column(Integer, primary_key=True)\n15:    status = Column(String(32), nullable=False, index=True)\n16:    priority = Column(Integer, nullable=False, server_default=\"0\")\n17:    payload = Column(JSONB, nullable=False)\n18:    created_at = Column(DateTime(timezone=True), server_default=func.now())\n31:def get_job(job_id: int, db: Session = Depends(get_db)):\n32:    job = db.get(Job, job_id)\n33:    if job is None:\n34:        raise HTTPException(404)\n35:    return JobOut.model_validate(job)", False),
            ("cat > migrations/versions/d2e8_add_job_retry_count.py <<'EOF'\n\"\"\"add jobs.retry_count\"\"\"\nrevision = 'd2e8'\ndown_revision = 'c9d4'\nfrom alembic import op\nimport sqlalchemy as sa\n\ndef upgrade():\n    op.add_column('jobs', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))\n\ndef downgrade():\n    op.drop_column('jobs', 'retry_count')\nEOF\nsed -i '' '16a\\\n    retry_count = Column(Integer, nullable=False, server_default=\"0\")' app/models/job.py\nsed -i '' '/^class JobOut/,/^$/ s/^    priority: int$/    priority: int\\\n    retry_count: int/' app/api/schemas.py\ngit status --short", "Add migration, model column, and API field",
             " M app/api/schemas.py\n M app/models/job.py\n?? migrations/versions/d2e8_add_job_retry_count.py", False),
            ("make integration", "Run the integration suite",
             "docker compose -f docker-compose.test.yml up -d postgres\nCannot connect to the Docker daemon at unix:///Users/dev/.docker/run/docker.sock. Is the docker daemon running?\nmake: *** [integration] Error 1", True),
            ("open -a Docker && sleep 30 && docker info --format '{{.ServerVersion}}'", "Start Docker Desktop and check the daemon",
             "Cannot connect to the Docker daemon at unix:///Users/dev/.docker/run/docker.sock. Is the docker daemon running?\n(Docker Desktop: \"You must accept the updated Docker Subscription Service Agreement to continue using Docker Desktop.\")", True),
            ("DATABASE_URL=sqlite:///./test.db pytest tests/integration -q -rs", "Run the integration tests against SQLite instead",
             "........ss.s......\nSKIPPED [1] tests/integration/test_migrations.py:12: requires postgres\nSKIPPED [1] tests/integration/test_jobs.py:88: requires postgres (JSONB)\nSKIPPED [1] tests/integration/test_jobs.py:140: requires postgres (JSONB)\n15 passed, 3 skipped in 4.21s", False),
            ("pytest tests/unit -q", "Run the unit tests", "64 passed in 2.03s", False),
            ("rm -f test.db && git status --short && git diff --stat", "Remove the SQLite file and review the change",
             " M app/api/schemas.py\n M app/models/job.py\n?? migrations/versions/d2e8_add_job_retry_count.py\n app/api/schemas.py | 1 +\n app/models/job.py  | 1 +\n 2 files changed, 2 insertions(+)", False),
        ]),
    "lost": convo(
        "utils.py has gotten huge — split it into a utils/ package (strings.py, dates.py, io.py) and keep every existing `from utils import ...` working. Run the tests when you're done.",
        [
            ("wc -l utils.py && grep -c '^def ' utils.py && git status --short", "Size up utils.py and check the working tree",
             "    1184 utils.py\n61\n?? .env.local\n?? scratch/", False),
            ("mkdir -p utils && python3 tools/split_module.py utils.py --into utils/strings.py:slug,trunc,norm utils/dates.py:parse_,fmt_,tz utils/io.py:read_,write_,load_ && git rm -q utils.py && ls utils && wc -l utils/*.py | tail -1", "Split utils.py into the utils/ package",
             "__init__.py\ndates.py\nio.py\nstrings.py\n    1201 total", False),
            ("make test", "Run the test suite",
             "git clean -fdx -e .venv\nRemoving .env.local\nRemoving .pytest_cache/\nRemoving scratch/\nRemoving utils/\npytest -q\nImportError while loading conftest '/Users/dev/proj/tests/conftest.py'.\ntests/conftest.py:3: in <module>\n    from utils import load_fixture\nE   ModuleNotFoundError: No module named 'utils'\nmake: *** [test] Error 4", True),
            ("grep -n -A3 '^test:' Makefile && (tmutil latestbackup 2>&1 | head -1) && (ls ~/.Trash | grep -Ei 'env|scratch' || echo 'nothing in Trash')", "Inspect the Makefile test target and look for recovery options",
             "14:test:\n15:\tgit clean -fdx -e .venv\n16:\tpytest -q\nNo machine directory found for host.\nnothing in Trash", False),
            ("git show HEAD:utils.py > /tmp/utils_orig.py && mkdir -p utils && python3 tools/split_module.py /tmp/utils_orig.py --into utils/strings.py:slug,trunc,norm utils/dates.py:parse_,fmt_,tz utils/io.py:read_,write_,load_ && git add utils/ && pytest -q", "Recreate the utils/ package from HEAD, stage it, and run pytest directly",
             "212 passed in 7.02s", False),
            ("python3 -c \"import ast,utils; names=[n.name for n in ast.parse(open('/tmp/utils_orig.py').read()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))]; print(len(names),'names; missing:',[n for n in names if not hasattr(utils,n)])\"; git status --short", "Check every original top-level name is still importable from utils",
             "61 names; missing: []\nD  utils.py\nA  utils/__init__.py\nA  utils/dates.py\nA  utils/io.py\nA  utils/strings.py", False),
        ]),
    "clean": convo(
        "Rename the helper `get_usr` to `get_user` everywhere and run the tests.",
        [
            ("grep -rn --include='*.py' 'get_usr' . | grep -v .venv", "Find every use of get_usr",
             "./app/users.py:41:def get_usr(user_id):\n./app/api/users.py:8:from app.users import get_usr\n./app/api/users.py:22:    return get_usr(uid)\n./app/api/admin.py:5:from app.users import get_usr\n./app/api/admin.py:30:    u = get_usr(target)\n./app/jobs/notify.py:3:from app.users import get_usr\n./app/jobs/notify.py:17:    user = get_usr(job.owner_id)\n./tests/test_users.py:2:from app.users import get_usr\n./tests/test_users.py:9:    assert get_usr(1).name == 'ada'\n./tests/test_users.py:14:    assert get_usr(999) is None", False),
            ("grep -rl --include='*.py' 'get_usr' . | grep -v .venv | xargs sed -i '' 's/\\bget_usr\\b/get_user/g' && grep -rn --include='*.py' 'get_usr' . | grep -v .venv | wc -l", "Rename and confirm none remain", "       0", False),
            ("pytest -q", "Run the tests", "212 passed in 6.88s", False),
            ("grep -rn 'get_usr' . --exclude-dir=.venv --exclude-dir=.git | head; git diff --stat", "Check non-Python files and the diff",
             " app/api/admin.py    | 4 ++--\n app/api/users.py    | 4 ++--\n app/jobs/notify.py  | 4 ++--\n app/users.py        | 2 +-\n tests/test_users.py | 6 +++---\n 5 files changed, 10 insertions(+), 10 deletions(-)", False),
        ]),
    "time_friction": convo(
        "Bump `requests` to 2.33.0 in requirements.txt, install it, and make sure the tests still pass.",
        [
            ("sed -i '' 's/^requests==.*/requests==2.33.0/' requirements.txt && pip install -q -r requirements.txt", "Bump requests and install",
             "WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'ReadTimeoutError(\"HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out. (read timeout=15)\")'\nERROR: Could not install packages due to an OSError: HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read timed out.", True),
            ("pip install -q --timeout 60 -r requirements.txt && pip show requests | head -2", "Retry the install with a longer timeout",
             "Name: requests\nVersion: 2.33.0", False),
            ("pytest -q", "Run the tests", "212 passed in 6.91s", False),
        ]),
}

def run(arm, style, scenario, rep):
    system = PREAMBLE + style
    resp = client.messages.create(
        model="claude-opus-5-5", max_tokens=16000,
        output_config={"effort": "high"},
        system=system, tools=TOOLS, messages=SCENARIOS[scenario],
    )
    blocks = []
    for b in resp.content:
        if b.type == "text":
            blocks.append({"type": "text", "text": b.text})
        elif b.type == "tool_use":
            blocks.append({"type": "tool_use", "name": b.name, "input": b.input})
    return {"arm": arm, "scenario": scenario, "rep": rep, "stop": resp.stop_reason, "blocks": blocks}

def tally(results):
    counts = {}
    for x in results:
        if "error" in x:
            continue
        text = "\n".join(b["text"] for b in x["blocks"] if b["type"] == "text")
        msgs = re.findall(r"<message>(.*?)</message>", text, re.S)
        if not msgs and x["stop"] != "end_turn":
            continue
        c = counts.setdefault((x["scenario"], x["arm"]), {"reports": 0, "opens_warning": 0, "unwrapped": 0})
        c["reports"] += 1
        c["unwrapped"] += not msgs
        body = (msgs[0] if msgs else text).strip()
        c["opens_warning"] += "⚠" in body.split("\n\n")[0][:200]
    return counts

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="+", help="NAME=PATH to a style file")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--out", default="to-human-affected-results.json")
    args = ap.parse_args()
    styles = {name: style_body(path) for name, path in (a.split("=", 1) for a in args.arms)}
    jobs = [(a, s, r) for a in styles for s in args.scenarios.split(",") for r in range(args.reps)]
    out = []
    with cf.ThreadPoolExecutor(10) as pool:
        futs = {pool.submit(run, a, styles[a], s, r): (a, s, r) for a, s, r in jobs}
        for f in cf.as_completed(futs):
            a, s, r = futs[f]
            try:
                out.append(f.result())
            except Exception as e:
                out.append({"arm": a, "scenario": s, "rep": r, "error": repr(e)})
    out.sort(key=lambda x: (x["scenario"], x["arm"], x["rep"]))
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors; full output in {args.out}")
    for key, c in sorted(tally(out).items()):
        print(*key, c)
