"""Hand-run micro-test for the to-human style's rule that what the agent needs
of the human is written in italics, wherever it falls in a message: it spends
model calls, so nothing runs it automatically.

Each scenario is a prefilled tool history under the full style, and the model
writes the turn's end, its tool calls answered with canned results for up to
three responses. Three scenarios need the human: `asked` (a product decision
the agent has already put to them through the async ask tool), `login` (a
staging deploy blocked on `gcloud auth login`, which only they can run, so a
`⚠ Critical` block is due too) and `value` (Sentry wired up, off until they
give the DSN). Two do not: `clean` (a rename that passes) and `emphasis`
(billing tests CI never collected, now running and passing: a finding that
invites emphasis). What the human reads is every message of the turn, a
`<message>` span or a message-tool call. Each run's italic spans (`*x*`,
`_x_`, outside code) are found by pattern; a judge that does not know the arm
then lists what the messages need of the human, whether each need is in
italics, and which italic spans are not a need. `block` counts the messages
that still carry a `> **Needs you:**` block of their own, outside the
critical block.

  python3 tests/output-styles/to-human-needs-you-eval.py ARM=STYLE.md [ARM=STYLE.md ...] \\
      [--reps 4] [--scenarios asked,login,value,clean,emphasis] [--out results.json]

e.g. control=<(git show HEAD~1:output-styles/to-human.md) variant=output-styles/to-human.md.
It calls api.anthropic.com directly with ANTHROPIC_API_KEY.

Results, 2026-10-25, claude-opus-5-5 at high effort, judge at low effort, 4
reps per arm and scenario (a run that is still calling tools after three
responses has not reported and is not counted). `asked` and `value` then had
gaps in their histories (an undefined decorator, missing imports) that sent
most runs off to verify, since mended:
  7.207.0 control      no need in italics; its own block in 4 of the 8
                       reports with a need (the rest stated it in the
                       critical block's Needs you line or in prose)
  italics, "Italics    the core need in italics in every report that had
  mark nothing else"   one (asked 2, login 4, value 0 reported); no block;
                       no italic span that was not a need
  italics, without     the same (asked 4, login 4, value 3); no block; one
  that sentence        span the judge called not a need was the rule's "why
                       it has to be them"
  every arm            no italics in clean or emphasis, control included:
                       opus does not italicize for emphasis here, so the
                       ban sentence had nothing to prevent; it shipped as
                       the rule's reason instead
Final wording (7.208.0), mended histories:
  shipped              the core need in italics in 10 of 10 reports with a
                       need (asked 2 of 4 reported, login 4, value 4), most
                       inside the critical block's Needs you line; the
                       needs left in roman were follow-ups of the italic one
                       ("tell me when you've signed in"); no block; no
                       stray italics; clean and emphasis 0 spans
"""
import argparse, importlib.util, json, re, sys, concurrent.futures as cf
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mid_turn import MESSAGE_TOOL, MESSAGE_TOOL_DEF, MESSAGE_RESULT, spans  # noqa: E402

_spec = importlib.util.spec_from_file_location("to_human_affected_eval", HERE / "to-human-affected-eval.py")
affected = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(affected)
client, convo, style_body, PREAMBLE = affected.client, affected.convo, affected.style_body, affected.PREAMBLE
ASK = "mcp__sminos__AskUserQuestion"
TOOLS = affected.TOOLS + [MESSAGE_TOOL_DEF]
ASKED = "Asked. The question waits in the human's view; their answer arrives in a later message."


def with_ask(msgs, questions):
    """The history with an async ask as its last step, answered as the ask tool answers one."""
    return msgs + [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "toolu_ask", "name": ASK, "input": {"questions": questions, "async": True}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "toolu_ask", "content": ASKED}]},
    ]


SCENARIOS = {
    "asked": with_ask(convo(
        "Add rate limiting to POST /v1/messages so one customer can't starve the others. Run the tests. I'm heading out, keep going without me.",
        [
            ("grep -n 'request.state' app/auth.py && psql -Atc \"select count(*), count(distinct org_id) from api_keys where revoked_at is null\" $DATABASE_URL",
             "Inspect how requests are keyed and count live keys per org",
             "16:    request.state.api_key_id = key.id\n17:    request.state.org_id = key.org_id\n2318|412", False),
            ("psql -Atc \"select org_id, count(*) from api_keys where revoked_at is null group by 1 order by 2 desc limit 3\" $DATABASE_URL",
             "See how keys are spread across orgs",
             "org_7f2|388\norg_a91|204\norg_03c|97", False),
            ("cat > app/ratelimit.py <<'EOF'\nimport functools\nfrom fastapi import HTTPException, Request\nfrom limits import RateLimitItemPerMinute, storage, strategies\nfrom app.config import settings\n\n_limiter = strategies.MovingWindowRateLimiter(storage.RedisStorage(settings.REDIS_URL))\n_limit = RateLimitItemPerMinute(settings.MESSAGES_PER_MINUTE)\n\ndef rate_limited(bucket):\n    def wrap(handler):\n        @functools.wraps(handler)\n        async def inner(request: Request, *args, **kwargs):\n            if not _limiter.hit(_limit, str(bucket(request))):\n                raise HTTPException(429, headers={'Retry-After': '60'})\n            return await handler(request, *args, **kwargs)\n        return inner\n    return wrap\nEOF\npython3 - <<'EOF'\nimport pathlib\np = pathlib.Path('app/api/messages.py'); s = p.read_text()\ns = s.replace('from app.auth import', 'from app.ratelimit import rate_limited\\nfrom app.auth import', 1)\np.write_text(s.replace('async def create_message(', '@rate_limited(bucket=lambda r: r.state.api_key_id)\\nasync def create_message(', 1))\nEOF\ngrep -n 'MESSAGES_PER_MINUTE' app/config.py && git diff --stat",
             "Add a per-key moving-window limiter on POST /v1/messages",
             "22:    MESSAGES_PER_MINUTE: int = 600\n app/api/messages.py | 2 ++\n 1 file changed, 2 insertions(+)", False),
            ("cat >> tests/api/test_messages.py <<'EOF'\n\ndef test_rate_limit_per_key(client, key_a, key_b, settings):\n    settings.MESSAGES_PER_MINUTE = 3\n    codes = [client.post('/v1/messages', headers={'x-api-key': key_a}, json=MSG).status_code for _ in range(4)]\n    assert codes == [200, 200, 200, 429]\n    assert client.post('/v1/messages', headers={'x-api-key': key_b}, json=MSG).status_code == 200\nEOF\npytest -q",
             "Add a test that one key over its limit gets 429 and another key does not, then run the tests",
             "222 passed in 7.61s", False),
        ]),
        [{"question": "Rate-limit POST /v1/messages per API key or per organization? One org holds 388 live keys, so a per-key limit lets it send 388x what a one-key org can; per-org caps it but also caps orgs that split traffic across teams on purpose.",
          "header": "Limit scope",
          "options": [{"label": "Per organization", "description": "One budget per org, shared by all its keys"},
                      {"label": "Per API key", "description": "One budget per key (what is implemented now)"}],
          "multiSelect": False}]),
    "login": convo(
        "Deploy the hotfix branch to staging and smoke-test /health. I'll check back tonight.",
        [
            ("git rev-parse --abbrev-ref HEAD && make build", "Confirm the branch and build the image",
             "hotfix/session-timeout\nSuccessfully built and pushed gcr.io/acme-staging/api:7c1e0d2", False),
            ("gcloud run deploy api --image gcr.io/acme-staging/api:7c1e0d2 --region us-central1 --project acme-staging --quiet",
             "Deploy the image to the staging Cloud Run service",
             "ERROR: (gcloud.run.deploy) There was a problem refreshing your current auth tokens: Reauthentication required.\nPlease run:\n\n  $ gcloud auth login\n\nto obtain new credentials.", True),
            ("gcloud auth list --format='value(account,status)' && gcloud auth print-access-token >/dev/null",
             "Check which accounts are credentialed and whether a token can be minted",
             "dev@acme.io\tACTIVE\nERROR: (gcloud.auth.print-access-token) Reauthentication required. Please run: $ gcloud auth login", True),
            ("ls ~/.config/gcloud/*.json 2>/dev/null; gcloud config configurations list --format='value(name,is_active)'",
             "Look for a service-account key or another configuration to deploy with",
             "default\tTrue", False),
        ]),
    "value": convo(
        "Wire up Sentry error reporting in the Flask app, then run the tests.",
        [
            ("grep -rn -i 'sentry' . --include='*.py' --include='*.toml' --include='*.env*' | grep -v .venv; env | grep -i sentry; ls .env* 2>/dev/null",
             "Look for any existing Sentry setup or DSN",
             ".env.example", False),
            ("pip install -q 'sentry-sdk[flask]==2.31.0' && echo 'sentry-sdk[flask]==2.31.0' >> requirements.txt && cat > app/observability.py <<'EOF'\nimport os\nimport sentry_sdk\n\ndef init_sentry():\n    if dsn := os.environ.get(\"SENTRY_DSN\"):\n        sentry_sdk.init(dsn=dsn, environment=os.environ.get(\"APP_ENV\", \"dev\"), traces_sample_rate=0.1)\nEOF\nsed -i '' 's/^def create_app():/from app.observability import init_sentry\\\n\\\ndef create_app():\\\n    init_sentry()/' app/__init__.py && echo 'SENTRY_DSN=' >> .env.example && grep -n -B1 -A2 'init_sentry' app/__init__.py",
             "Install sentry-sdk, initialize it from SENTRY_DSN in create_app, and document the variable",
             "6:from app.observability import init_sentry\n7:\n8:def create_app():\n9:    init_sentry()\n10:    app = Flask(__name__)", False),
            ("pytest -q && SENTRY_DSN=https://public@o0.ingest.sentry.io/0 python3 -c \"import sentry_sdk; from app import create_app; create_app(); print(sentry_sdk.get_client().is_active())\"",
             "Run the tests and check the SDK activates when a DSN is set",
             "188 passed in 5.12s\nTrue", False),
        ]),
    "clean": affected.SCENARIOS["clean"],
    "emphasis": convo(
        "CI is green but the coverage report says 0% for app/billing. Find out why and fix it.",
        [
            ("grep -n -A4 '\\[tool.pytest' pyproject.toml && ls tests/ tests/billing | head -20",
             "Read the pytest config and list the test directories",
             "31:[tool.pytest.ini_options]\n32:testpaths = [\"tests/unit\", \"tests/api\"]\n33:addopts = \"-q --cov=app\"\napi\nbilling\nunit\ntests/billing:\ntest_invoices.py\ntest_proration.py\ntest_refunds.py", False),
            ("git log --format='%h %ad %s' --date=short -1 -- tests/billing && git log --format='%h %ad %s' --date=short -S'testpaths' -- pyproject.toml",
             "See when the billing tests and the testpaths line were added",
             "e41b09a 2025-03-02 billing: proration tests\n9d2c771 2024-11-18 pytest: restrict testpaths to unit and api", False),
            ("sed -i '' 's/testpaths = \\[\"tests\\/unit\", \"tests\\/api\"\\]/testpaths = [\"tests\"]/' pyproject.toml && pytest tests/billing -q && pytest -q | tail -3",
             "Collect every test directory and run the billing tests, then the whole suite",
             "41 passed in 1.88s\n----------- coverage: platform darwin, python 3.13 -----------\napp/billing      87%\n290 passed in 9.31s", False),
        ]),
}


def canned(block):
    return {MESSAGE_TOOL: MESSAGE_RESULT, ASK: ASKED}.get(block.name, "(no output)")


def run(arm, style, scenario, rep, max_steps=3):
    system = PREAMBLE + style
    msgs, steps = SCENARIOS[scenario], []
    for _ in range(max_steps):
        resp = client.messages.create(model="claude-opus-5-5", max_tokens=16000, output_config={"effort": "high"},
                                      system=system, tools=TOOLS, messages=msgs)
        blocks = []
        for b in resp.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "name": b.name, "input": b.input})
        steps.append({"stop": resp.stop_reason, "blocks": blocks})
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            break
        msgs = msgs + [{"role": "assistant", "content": resp.content},
                       {"role": "user", "content": [{"type": "tool_result", "tool_use_id": b.id, "content": canned(b)} for b in uses]}]
    return {"arm": arm, "scenario": scenario, "rep": rep, "steps": steps}


def messages(x):
    """What the human reads of the run: its spans and message-tool calls, in order."""
    out = []
    for step in x["steps"]:
        for b in step["blocks"]:
            if b["type"] == "text":
                out += [s.strip() for s in spans(b["text"]) if s.strip()]
            elif b["name"] == MESSAGE_TOOL and str(b["input"].get("text", "")).strip():
                out.append(b["input"]["text"].strip())
    return out


CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
ITALIC = re.compile(r"(?<![*\w\\])\*(?![*\s])((?:(?!\n\n)[^*])+?)(?<![\s\\])\*(?![*\w])"
                    r"|(?<![_\w\\])_(?![_\s])((?:(?!\n\n)(?:[^_]|(?<=\w)_(?=\w)))+?)(?<![\s\\])_(?![_\w])", re.S)


def italics(text):
    """The italic spans of a message: emphasis by one marker, bold markers removed first, markers in code masked."""
    prose = CODE.sub(lambda m: m.group(0).replace("*", "\x00").replace("_", "\x01"), text).replace("**", "").replace("__", "")
    return [(a or b).strip().replace("\x00", "*").replace("\x01", "_") for a, b in ITALIC.findall(prose)]


def own_block(text):
    """True when a blockquote that is not the critical block carries a `Needs you:` label."""
    quotes = re.findall(r"(?:^[ \t]*>.*(?:\n|$))+", text, re.M)
    return any(re.search(r"Needs you:", q) and "⚠" not in q for q in quotes)


JUDGE = """An agent sent its human the messages below; the human reads only these, not the agent's work. Answer from what the messages say.

needs: everything the messages need of the human: an action only they can take, a decision, access, a value, an answer to a question put to them. An optional offer they may take or leave ("I can also do X if you want") is not a need. For each, a few words for what it is, and whether the messages write that need (what is needed of them) in italics, as *text* or _text_ (bold, **text**, is not italics).
spans: for each italic span listed under <italics>, in that order, whether it states (part of) a need of the human.

Reply with only a JSON object: {"needs": [{"what": ..., "italic": true|false}], "spans": [true|false, ...]}

<messages>
%s
</messages>

<italics>
%s
</italics>"""


def judge(text, spans_found):
    resp = client.messages.create(
        model="claude-opus-5-5", max_tokens=4000, output_config={"effort": "low"},
        messages=[{"role": "user", "content": JUDGE % (text, "\n".join(f"- {s}" for s in spans_found) or "(none)")}],
    )
    out = "".join(b.text for b in resp.content if b.type == "text")
    return json.loads(re.search(r"\{.*\}", out, re.S).group(0))


def ended(x):
    """True when the run's turn ended: its last response called no tool, or only the message tool (that call is the turn's last word)."""
    last = x["steps"][-1]["blocks"] if x.get("steps") else []
    return all(b["name"] == MESSAGE_TOOL for b in last if b["type"] == "tool_use")


def tally(results):
    counts = {}
    for x in results:
        c = counts.setdefault((x["scenario"], x["arm"]), {"runs": 0, "reported": 0, "block": 0, "italic_spans": 0,
                                                          "stray_spans": 0, "needs": 0, "needs_italic": 0, "asked_again": 0})
        c["runs"] += 1
        if "error" in x or not x.get("messages") or not ended(x):
            continue
        c["reported"] += 1
        c["block"] += any(own_block(m) for m in x["messages"])
        c["italic_spans"] += len(x["italics"])
        c["asked_again"] += any(b["type"] == "tool_use" and b["name"] == ASK for s in x["steps"] for b in s["blocks"])
        if (j := x.get("judged")) and "error" not in j:
            c["stray_spans"] += sum(not s for s in j.get("spans", []))
            c["needs"] += len(j.get("needs", []))
            c["needs_italic"] += sum(bool(n.get("italic")) for n in j.get("needs", []))
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("arms", nargs="+", help="NAME=PATH to a style file")
    ap.add_argument("--reps", type=int, default=4)
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--out", default="to-human-needs-you-results.json")
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
    for x in out:
        if "error" not in x:
            x["messages"] = messages(x)
            x["italics"] = [s for m in x["messages"] for s in italics(m)]
    with cf.ThreadPoolExecutor(10) as pool:
        futs = {pool.submit(judge, "\n\n---\n\n".join(x["messages"]), x["italics"]): x for x in out if x.get("messages")}
        for f in cf.as_completed(futs):
            try:
                futs[f]["judged"] = f.result()
            except Exception as e:
                futs[f]["judged"] = {"error": repr(e)}
    out.sort(key=lambda x: (x["scenario"], x["arm"], x["rep"]))
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(out)} runs, {sum('error' in x for x in out)} errors; full output in {args.out}")
    for key, c in sorted(tally(out).items()):
        print(*key, c)
