# archive/

A bare directory name is this directory's; `skills/…` paths are the repository's.

Retired skills and agents kept for reference; no harness loads anything here.

- `codex-migration/`: moved a Claude Code session into Codex as a resumable thread.
- `experimental-context/`: the keyed `<revisit>` re-injection mode, with its skill, hooks and test, unwired.
- `domain-modeling/`: the CONTEXT.md glossary and ADR convention.
- `execplan/`, `writing-plans/`: the single-ExecPlan skill and the execution-plan skill, both folded into the living spec; their surviving rules live in `skills/execspec/references/living-spec.md`, stated in its own words; the vendored Codex PLANS.md they came from stays at `execplan/references/PLANS.md`.
- `qa-loop/`: the board seats' PR review loop agent, dormant with board dispatch. The dormant protocols in `skills/issue-tracker/` still name `doperpowers:qa-loop`; re-arming them means moving `qa-loop.md` back under `agents/`.
- `codex-companion/`: the skill that drove OpenAI's vendored Codex companion runtime, replaced by the native Codex agent ports and `review-code`. Its tests moved with it, and the review bench's `--engine codex` baseline still runs the runtime from here, so it is not dead code.
