"""`live.sh race` (acceptance 23): whether a claim's confirming read sees
every earlier claim comment, measured against real GitHub.

Each round opens one fresh ticket and starts five `task claim` processes,
each with a session id, a thread id and an address of its own from the
stand-in sminos, and an index (TASK_HOME) of its own. Each is held at the
barrier after a first read that found the ticket unheld and after every
call it makes before its append; it says so in its trace as it arrives,
and when all five are there they are let go together, so the round has five appends in
competition. Each records (TASK_TRACE) which claim comments its confirming
read saw, and is held again until all five reads are recorded, so that no
loser deletes its record before every read has been captured. A round in
which any claimant did not reach the barrier is run again and not counted.

    python3 live_race.py <owner/name> <the task launcher> [rounds]

It prints the measurement and exits 0 only for: every round one exit 0, no
confirming read that missed a claim comment of a lower id than the
reader's own, and a fresh `task show --json` naming each round's winner."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
STANDIN_SMINOS = HERE / "standin" / "sminos"
CLAIMANTS = 5
WAIT = 90


def claimant(i):
    """An invented identity: session, thread, address."""
    session = "%08x-0000-4000-8000-%012x" % (0xace00000 + i, i)
    thread = "%08x-0000-4000-8000-%012x" % (0xbee00000 + i, i)
    return session, thread, "racer%d#%s (race on bench)" % (i, session[:8])


def run(argv, env, check=True):
    done = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=180)
    if check and done.returncode != 0:
        raise SystemExit("live race: %s exited %d: %s" % (" ".join(argv[:3]), done.returncode, done.stderr.strip()))
    return done


def traces(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def wait_for(procs, paths, read, deadline):
    """Until every claimant has a trace of `read` or has exited."""
    while time.monotonic() < deadline:
        if all(any(t["read"] == read for t in traces(p)) or proc.poll() is not None
               for proc, p in zip(procs, paths)):
            return
        time.sleep(0.05)


def main(repo, task, rounds):
    work = pathlib.Path(tempfile.mkdtemp(prefix="task-race-"))
    base = dict(os.environ)
    base.pop("CLAUDE_CODE_SESSION_ID", None)
    driver = dict(base, TASK_HOME=str(work / "driver-home"), TASK_SMINOS="")
    state = work / "sminos.json"
    sm = {"addresses": {}, "threads": {}, "say": {"exit": 0}}
    for i in range(1, CLAIMANTS + 1):
        session, thread, address = claimant(i)
        sm["addresses"][session] = address
        answer = {"thread": thread, "session": session, "short": session[:8], "alias": "racer%d" % i,
                  "opened": "2026-11-27T00:00:00Z", "state": "busy", "ended": False, "local": True,
                  "machine": "bench", "project": {"id": "p-race", "name": "race"}, "not_carried": ""}
        sm["threads"][session] = sm["threads"][thread] = answer
    state.write_text(json.dumps(sm))
    body = work / "body.md"
    body.write_text("A scratch ticket of task/tests/live.sh race: five claimants race for it; closed by it.\n")
    counted, tries, results = 0, 0, []
    while counted < rounds and tries < rounds + 10:
        tries += 1
        made = run([task, "create", "live race: round %d" % tries, "--repo", repo, "--category", "spike",
                    "--priority", "P3", "--readiness", "ready-to-work", "--horizon", "expected", "--body-file",
                    str(body)], driver)
        number = made.stdout.split()[0]
        here = work / ("round-%d" % tries)
        here.mkdir()
        barrier = here / "go"
        paths, procs = [], []
        for i in range(1, CLAIMANTS + 1):
            session, _, _ = claimant(i)
            path = here / ("trace-%d.jsonl" % i)
            env = dict(base, CLAUDE_CODE_SESSION_ID=session, TASK_SMINOS=str(STANDIN_SMINOS),
                       TASK_SMINOS_STATE=str(state), TASK_HOME=str(here / ("home-%d" % i)),
                       TASK_CLAIM_BARRIER=str(barrier), TASK_TRACE=str(path))
            paths.append(path)
            procs.append(subprocess.Popen([task, "claim", number, "--repo", repo], env=env, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True))
        wait_for(procs, paths, "at-barrier", time.monotonic() + WAIT)
        reached = all(any(t["read"] == "first" and t["holder"] is None for t in traces(p))
                      and any(t["read"] == "at-barrier" for t in traces(p)) and proc.poll() is None
                      for proc, p in zip(procs, paths))
        barrier.write_text("go\n")
        if reached:
            wait_for(procs, paths, "confirm", time.monotonic() + WAIT)
        pathlib.Path(str(barrier) + ".confirmed").write_text("go\n")
        outs = [proc.communicate(timeout=180) for proc in procs]
        codes = [proc.returncode for proc in procs]
        confirms = [next((t for t in traces(p) if t["read"] == "confirm"), None) for p in paths]
        if not reached or any(c is None for c in confirms):
            print("round %d (#%s): not counted: a claimant did not reach the barrier or append (exits %s)"
                  % (tries, number, codes))
            for (out, err), code in zip(outs, codes):
                if code not in (0, 3):
                    print("  exit %d: %s" % (code, err.strip()))
        else:
            owns = [c["own"] for c in confirms]
            missed = [(c["own"], o) for c in confirms for o in owns if o < c["own"] and o not in c["claims"]]
            shown = json.loads(run([task, "show", number, "--repo", repo, "--json"], driver).stdout)
            winners = [owns[i] for i, code in enumerate(codes) if code == 0]
            agrees = shown["holder"] is not None and winners == [shown["holder"]["claim"]]
            counted += 1
            results.append({"round": counted, "number": int(number), "exits": codes, "owns": owns,
                            "missed": missed, "show_agrees": agrees})
            print("round %d (#%s): exits %s; winners %d; missed lower claims %d; show names the winner: %s"
                  % (counted, number, codes, len(winners), len(missed), agrees))
        closed = run([task, "close", number, "--repo", repo, "--not-planned", "--force", "live race round done"],
                     driver, check=False)
        if closed.returncode != 0:  # the round still counts; the ticket is left open, and says so
            print("  #%s was not closed (exit %d): %s" % (number, closed.returncode, closed.stderr.strip()))
        time.sleep(3)  # GitHub's limit on content writes per minute
    one = sum(1 for r in results if r["exits"].count(0) == 1)
    missed = sum(len(r["missed"]) for r in results)
    agree = sum(1 for r in results if r["show_agrees"])
    print("measured %s: %d rounds, %d appends in competition each; one winner in %d of %d; confirming reads that "
          "missed a lower claim: %d; show agrees in %d" % (time.strftime("%Y-%m-%d"), len(results), CLAIMANTS, one,
                                                            len(results), missed, agree))
    ok = len(results) == rounds and one == rounds and missed == 0 and agree == rounds
    if not ok:
        print(json.dumps(results, indent=1), file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 20))
