"""The grader: `claude -p` on opus, with no tools, sees the question, the
answer key and the run's final text with paths, tool names and line
citations masked, so it cannot tell the configurations apart.

    python3 -I web/evals/grade.py <runs dir> [--tasks <file>] [--regrade]

grades the run files there that have no verdict yet (all of them with
--regrade). run.py grades each run as it finishes, through the same code.
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402

GRADER_MODEL = 'opus'
GRADER_TIMEOUT_S = 300

GRADER_SYSTEM = """You grade one answer an AI agent gave to a research question about a web page.
You get the question, the answer key (numbered facts), and the agent's answer.
For each fact, decide whether the answer states it correctly: the same value, name,
number or code, allowing a different wording, order, formatting, units written another
way, or extra correct detail. Code, and any text a fact calls verbatim, must match the
key's text apart from whitespace and indentation, unless the fact says otherwise. A fact the answer leaves out, hedges
between alternatives, or gets wrong is false. Do not use your own knowledge of the page;
grade against the key. Ignore citations, references and how the agent says it got the page.
Reply with one JSON object and nothing else:
{"verdict": "correct" | "partial" | "wrong", "facts": {"<fact id>": true | false}, "note": "<one sentence on what was missing or wrong, or empty>"}
"correct" means every fact is true, "partial" some, "wrong" none."""

# A file URI whole, fragment (`#L12`) included, before the paths inside it are seen.
# Only real URI syntax: the scheme at a word boundary, then `//` and a path, so code or prose that
# says "file:" (a log line's `Line from file: ${line}`) is left alone.
_FILE_URI = re.compile(r'(?<![\w.+-])file://[^\s)\]>\'"`]*/[^\s)\]>\'"`]*')
# What is left of a cache path that is not absolute, and a generation folder's name anywhere.
_CACHE = re.compile(r'[^\s()\[\]<>\'"`]*\.cache/claude-web[^\s)\]>\'"`,;]*|\b\d{8}T\d{9}Z-[0-9a-f]{4}\b')
_LINE_ANCHOR = re.compile(r'#L\d+(?:\s*[–-]\s*L?\d+)?')
# Absolute paths under the roots a run's files live in (a temporary HOME, the cache).
_PATH = re.compile(r'(?<![\w.:/])(?:~|/private)?/(?:var|tmp|Users|home|private|opt)/[^\s)\]\'"`,;]*'
                   r'|(?<![\w.:/])~/[^\s)\]\'"`,;]*')
_TOOL = re.compile(r'\b(?:mcp__web__fetch|web__fetch|WebFetch)\b')
_LINE_CITE = re.compile(r'\[L\d[\d,]*(?:\s*[–-]\s*L?\d[\d,]*)?(?:\s*[,;]\s*L?\d[\d,]*(?:\s*[–-]\s*L?\d[\d,]*)?)*\]')
_LINE_REF = re.compile(r'\b[Ll]ines?\s+\d[\d,]*(?:\s*(?:[–-]|to)\s*\d[\d,]*)?|\bL\d{2,}(?:\s*[–-]\s*L?\d+)?\b')
_FILES = re.compile(r'\bclaude-web\b|\bpage\.(?:md|txt|pdf|json)\b|\bassets/\d+\.\w+')


def mask(text):
    """The answer with what tells the configurations apart replaced."""
    text = _FILE_URI.sub('<path>', text)
    text = _CACHE.sub('<path>', text)
    text = _PATH.sub('<path>', text)
    text = _LINE_ANCHOR.sub('', text)
    text = _TOOL.sub('<fetch tool>', text)
    text = _LINE_CITE.sub('[ref]', text)
    text = _LINE_REF.sub('<lines>', text)
    return _FILES.sub('<file>', text)


def grader_prompt(task, answer):
    facts = '\n'.join(f"{f['id']}: {f['claim']}" for f in task['facts'])
    return (f"Question:\n{task['question']}\n\nAnswer key:\n{facts}\n\n"
            f"The agent's answer:\n<answer>\n{mask(answer)}\n</answer>")


def parse_grade(text, fact_ids):
    """The grader's JSON, with the verdict recomputed from the facts (its definition); None when unreadable."""
    for m in re.finditer(r'\{', text):
        try:
            o, _ = json.JSONDecoder().raw_decode(text[m.start():])
        except ValueError:
            continue
        if not isinstance(o, dict) or not isinstance(o.get('facts'), dict):
            continue
        facts = {fid: o['facts'].get(fid) is True for fid in fact_ids}
        n = sum(facts.values())
        verdict = 'correct' if n == len(facts) else 'wrong' if n == 0 else 'partial'
        return {'verdict': verdict, 'facts': facts, 'note': str(o.get('note') or '')}
    return None


def grade(task, answer, workdir):
    """One grading call (retried once when its reply cannot be read). Returns (grade or None, usage record)."""
    usage = {'model': GRADER_MODEL, 'usageByModel': {}, 'costUsd': 0.0, 'durationMs': 0, 'attempts': 0}
    if not answer.strip():
        return {'verdict': 'wrong', 'facts': {f['id']: False for f in task['facts']}, 'note': 'no final answer'}, usage
    args = ['claude', '-p', '--model', GRADER_MODEL, '--output-format', 'json',
            '--tools', '', '--strict-mcp-config', '--disable-slash-commands',
            '--system-prompt', GRADER_SYSTEM, '--', grader_prompt(task, answer)]
    for _ in range(2):
        home = harness.make_home(workdir)
        cwd = tempfile.mkdtemp(prefix='grade-', dir=workdir)
        try:
            out, err, rc, timed_out, _ = harness.run_claude(args, cwd, harness.run_env(home), GRADER_TIMEOUT_S)
        finally:
            shutil.rmtree(home, ignore_errors=True)
            shutil.rmtree(cwd, ignore_errors=True)
        usage['attempts'] += 1
        try:
            res = json.loads(out)
        except ValueError:
            res = {}
        for model, u in (res.get('modelUsage') or {}).items():
            acc = usage['usageByModel'].setdefault(model, {})
            for k, v in u.items():
                if isinstance(v, (int, float)) and k not in ('contextWindow', 'maxOutputTokens'):
                    acc[k] = acc.get(k, 0) + v
                elif k == 'costBasis':
                    acc[k] = v  # 'list' when Claude Code knows the model's price, 'unknown' when it guessed
        usage['costUsd'] += res.get('total_cost_usd') or 0.0
        usage['durationMs'] += res.get('duration_ms') or 0
        g = parse_grade(res.get('result') or '', [f['id'] for f in task['facts']])
        if g:
            return g, usage
        usage['lastError'] = ('timed out' if timed_out else f'exit {rc}: {(err or out)[-300:]}')
    return None, usage


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs')
    ap.add_argument('--tasks', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.json'))
    ap.add_argument('--regrade', action='store_true')
    a = ap.parse_args()
    with open(a.tasks) as f:
        tasks = {t['id']: t for t in json.load(f)}
    work = tempfile.mkdtemp(prefix='web-evals-grade-')
    try:
        _grade_folder(a, tasks, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _grade_folder(a, tasks, work):
    for name in harness.run_files(a.runs):
        path = os.path.join(a.runs, name)
        with open(path) as f:
            r = json.load(f)
        if 'verdict' in r and not a.regrade:
            continue
        g, usage = grade(tasks[r['task']], r.get('finalText', ''), work)
        r['grade'] = usage
        if g:
            r.update(g)
        write_json(path, r)
        print(f"{name}: {r.get('verdict', 'ungraded')}")


def write_json(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


if __name__ == '__main__':
    main()
