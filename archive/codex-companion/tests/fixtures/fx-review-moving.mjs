// A review whose base ref MOVES after the call was keyed. The wire target is a
// symbolic branch name, so the worker reviews whatever the ref points at when
// it reads the diff — which need not be the commit the journal key names.
// The move happens on the next tick after the call is issued (leafCall yields
// on the semaphore first), so the worker runs against the moved ref.
import { spawnSync } from "node:child_process";

export default async function run({ review, args }) {
  const pending = review({ base: "main", label: "sweep" });
  spawnSync("git", ["branch", "-f", "main", args.moveTo], { cwd: args.repo });
  return pending;
}
