# task/

A path here is named from `task/` when it is the plugin's own file; `docs/` and `.github/` paths are the repository's.

A sixth plugin in this marketplace (versioned on its own: `scripts/bump-version.sh --plugin task`), the `task` command: the agents' one command for tracked work, which works tickets on a repository's GitHub board and tasks on the human's board, which sminos keeps. Design, decisions and the milestones still to come: `docs/doperpowers/specs/2026-11-24-ticket-board-design.md`; the human's board's verbs, `docs/doperpowers/specs/2026-11-27-task-board-design.md`. How the code meets it is each module's docstring.

## Map

- `bin/task` runs `cli/main.py` (the verbs and their flags): Python 3.9 and the standard library only, importing nothing of doperpowers or sminos.
- `cli/config.py`: which board a command works, and whether `task` may work it.
- `cli/github.py`: all GitHub access.
- `cli/record.py`: the record block (`task-record`) and the body digest. `cli/board.py`: the label vocabulary and a ticket as the reading verbs print it, trust and takeability included. `cli/lint.py`: the lint.
- `cli/verbs.py`: the ticket verbs. `cli/claiming.py`: the claim verbs (`claim`, `release`, `takeover`, `close`, `held`, `settle`) and each verb's housekeeping on its board.
- `cli/claims.py`: the claim record (`task-claim`) and the fold. `cli/index.py`: the machine's index (`$TASK_HOME/claims.json`). `cli/settle.py`: settle, `converge` (the label) and `write_release`.
- `cli/migrate.py`: the one-time relabel (`migrate plan`, `migrate apply`); `cli/legacy.py`: what the old board left in a body.
- `cli/sminos_client.py`: what `task` asks sminos.
- `cli/human.py`: the human's board's verbs, recognized before anything of the ticket board and run as `sminos task`.

## Traps

Each is held where it names; read that before changing the behaviour.

- **The board is the designated remote's, as last fetched.** In a clone its configuration is read from `refs/remotes/<remote>/HEAD`, never the working tree, and nothing fetches; a board not bound to `task` is refused before any call to GitHub (`config.py`): a branch's own copy is not the board's word. Under `--repo` there is no clone: the file is read from the repository's default branch on GitHub (`config.from_github`), and the refusal follows that read.
- **Every GitHub call names its host and its repository**: `gh api --hostname github.com`, never `gh issue` or `{owner}`, which `GH_HOST`, a client default or an `upstream` remote send elsewhere (`github.py`). Label writes are single adds and removes: a replacement drops a label another writer just set.
- **Comment ids are `fullDatabaseId`**, and a comment's number is resolved as an issue first, since GitHub's comment endpoint takes a pull request's number (`github._COMMENTS`, `verbs.comment`).
- **A body file is prose.** One that opens a `task-record` or `task-claim` fence is refused, and between prose and block the CLI writes and takes away exactly `record.SEPARATOR`, so a change of the record alone leaves the prose's bytes (`verbs.read_body_file`, `record.py`).
- **Cross-repository blockers** are taken while `board.CROSS_REPOSITORY_BLOCKED_BY` is true (`live.sh edge` found GitHub keeps them).
- **Who holds is the fold, never the `claimed` label** (`claims.py`): over the trusted records of the ticket's open interval, which every reader computes alike; `converge` makes the label agree.
- **A claim's order is what makes a crash come out right** (`claiming.py`'s docstring): nothing is written before sminos gives a definite answer about the session's thread (`my_thread`; a definite answer may name no thread), and the pending row with its attempt token exists before every append: the first (`index.add` in `_claim_one`) and a retry's (`index.renew`). The outcome is judged on the read `converge` returns last (`_claim_one`).
- **The index lock is never held across a call to GitHub or sminos**, so a transition decided before a call names the states it was decided from (`index.change`'s `expect`): a stale settle once turned a takeover's lapse back to held.
- **Housekeeping runs after a verb's preflight** and is bounded and shared (`claiming.housekeep`, `settle.run`): a verb that refuses in its preflight has written nothing, and one whose judgment housekeeping can change judges again after it; a refusal after housekeeping ran may follow an owed release it wrote (`claiming.housekeep`'s docstring). A pass reads each board's configuration before it writes there, unless its verb has just read it (`settle.run`'s `verified`; `settle._bound_to_task`).
- **Settle is asked, never told** (`settle.py`'s docstring): only sminos's answer for that very thread id, of this machine, saying it ended, releases; an owed release waits on the answer of that moment (`settle._settle_row`). Who holds, for `release`, `close` and `takeover`, is `claiming.holds`.
- **The relabel writes only what was reviewed.** `plan` writes a private file outside every git work tree (`migrate._inside_a_work_tree`, `_write_private`); `apply` refuses a malformed or undecided plan before any write and takes up only a state its write order leaves (`_on_the_path`); the body rewrite changes its spans and no other byte, and names no host (`legacy.py`).
- **`task held` and `task settle` are sminos's interface** (§9 of the spec, frozen at M3's review; M6 builds the calls): change them only with sminos's side (`claiming.held`, `claiming.settle`).
- `TASK_CLAIM_BARRIER`, `TASK_TRACE`, `TASK_SETTLE_EVERY` and `TASK_SETTLE_DEADLINE` are test seams, off or at their defaults unless set.

## Tests

`tests/run.sh` is the `task` gate: the CLI run as a process against `tests/standin/gh` (a `gh api` over a JSON state file, every call logged, its `hooks` playing another writer at a chosen call; its docstring) and `tests/standin/sminos`, fixtures in `tests/harness.py`, every name invented. `tests/live.sh <case>` runs against real GitHub on the private scratch repositories `TASK_LIVE_REPO` and `TASK_LIVE_REPO2` name (its header lists the cases and what each refuses), and is never part of the gate.
