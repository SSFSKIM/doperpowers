#!/usr/bin/env bash
#
# Cross-doc reference lint: the routed board schema (ticket-gate.md, park
# discriminant, worker bootstraps) bets correctness on file references
# resolving at runtime. This linter walks every skill markdown file and
# fails on references that resolve nowhere:
#   - {{BOARD_SCRIPTS}}/../references/*.md and <BOARD_SCRIPTS>/../ variants
#     (must exist under skills/issue-tracker/)
#   - references/*.{md,sh,yml} and scripts/*.sh mentions (must exist
#     relative to the file, its skill root, or a skill named in the same
#     paragraph — prose wraps lines, so context is paragraph-scoped)
#   - doperpowers:<name> references (must be a skill directory, an agent
#     definition under agents/, or a workflow the plugin manifest registers —
#     its `workflows` entries, each file's `meta.name`)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

python3 - "$REPO_ROOT" <<'EOF'
import re, sys, pathlib

root = pathlib.Path(sys.argv[1]) / "skills"
skills = {p.name for p in root.iterdir() if p.is_dir()}
agents = {p.stem for p in (pathlib.Path(sys.argv[1]) / "agents").glob("*.md")}

# Named workflows: `doperpowers:<meta.name>` for every .js the manifest's
# `workflows` key names (a file or a directory of them), as the engine
# registers them.
import json
repo = pathlib.Path(sys.argv[1])
manifest = json.loads((repo / ".claude-plugin" / "plugin.json").read_text())
declared = manifest.get("workflows", [])
workflows = set()
for entry in ([declared] if isinstance(declared, str) else declared):
    path = repo / entry
    files = sorted(path.glob("*.js")) if path.is_dir() else [path]
    for js in files:
        m = re.search(r"export\s+const\s+meta\s*=\s*\{[^}]*?\bname:\s*['\"]([^'\"]+)['\"]", js.read_text())
        if m:
            workflows.add(m.group(1))
fails, checked = [], 0

def paragraphs(text):
    """Yield (start_line, paragraph_text) for blank-line-delimited blocks."""
    buf, start = [], 1
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip():
            if not buf:
                start = i
            buf.append(line)
        elif buf:
            yield start, "\n".join(buf)
            buf = []
    if buf:
        yield start, "\n".join(buf)

for f in sorted(root.rglob("*.md")):
    text = f.read_text()
    my_skill = f.relative_to(root).parts[0]
    for start, para in paragraphs(text):
        for m in re.finditer(
            r'(?:\{\{BOARD_SCRIPTS\}\}|<BOARD_SCRIPTS>)/\.\./(references/[A-Za-z0-9._-]+\.md)',
            para,
        ):
            checked += 1
            target = root / "issue-tracker" / m.group(1)
            if not target.exists():
                fails.append(f"{f}:{start}: BOARD_SCRIPTS-relative -> missing {target}")
        for pattern, kind in (
            (r'(?<![./A-Za-z0-9_-])(references/[A-Za-z0-9._-]+\.(?:md|sh|yml|yaml))', "references"),
            (r'(?<![./A-Za-z0-9_-])(scripts/[A-Za-z0-9._-]+\.sh)', "scripts"),
        ):
            for m in re.finditer(pattern, para):
                checked += 1
                rel = m.group(1)
                candidates = [f.parent / rel, root / my_skill / rel]
                candidates += [root / s / rel for s in skills if s in para]
                if not any(c.exists() for c in candidates):
                    fails.append(f"{f}:{start}: {kind}-path resolves nowhere: {rel}")
        for m in re.finditer(r'doperpowers:([a-z0-9-]+)', para):
            checked += 1
            if m.group(1) not in skills and m.group(1) not in agents and m.group(1) not in workflows:
                fails.append(f"{f}:{start}: dangling reference doperpowers:{m.group(1)}")

print(f"checked {checked} references across {len(skills)} skills, {len(agents)} agents, {len(workflows)} workflows")
if fails:
    print(f"{len(fails)} DANGLING:")
    for x in fails:
        print("  " + x)
    sys.exit(1)
print("all cross-doc references resolve")
EOF
