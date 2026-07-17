# Implement worker — decomposition procedure

Opened on demand by an implement worker whose Check-2 verdict is "too big,
and the remainder CAN be written down as self-contained child pre-specs
right now". Your spawn prompt carries the INSTANCE facts — your ticket
number and the board scripts directory (BOARD_SCRIPTS); this file carries
only the PROCEDURE and grants no authority beyond your prompt's.

1. Register the children with typed edges:
   `<BOARD_SCRIPTS>/board-register.sh "<title>" <bug|enhancement|spike> <P0..P3> --parent <your-ticket>`
   - spike = a child whose deliverable is findings the other children
     need — usually their `--blocked-by`.
   - `--blocked-by` between siblings where order matters; a chain IS
     serialization (serial vs parallel is a dependency shape, not a
     policy branch).
   - `--state S --note "<why>"` for a child born parked.

2. Flesh out each child body (`gh issue edit <n> --body-file -`) to the
   pre-spec bar: a fresh-context worker can start from the body alone.

3. Gate-triage each child HONESTLY per the doperpowers:issue-tracker
   ticket contract and park discriminant — `ready-for-agent` only if YOU
   believe it passes the Ticket Gate
   (`<BOARD_SCRIPTS>/../references/ticket-gate.md`).

4. Register only children you can spec self-contained NOW. Contingent
   later phases live as a `## Roadmap` section in the parent body — the
   worker finishing phase K registers phase K+1 at PR time.

5. Update the parent: the roadmap plus a Decision log entry saying why
   this cut. The parent becomes an epic (never dispatched; the sweeps move
   it).

6. End your turn. The decomposing worker writes NO code — recursion is
   emergent: each child's worker re-runs the same gate from fresh context.
