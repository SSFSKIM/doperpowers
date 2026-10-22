# devcloud: `down` on a partially booted host (board ticket 121)

Branch `devcloud-down-partial`, off main at `7acef18a`. Implementation commit `5bd7a929`; devcloud
0.9.3. PR: #347. Built by a plan-executor run on astra, at the person's instruction to keep
subagents off the Claude weekly limits. The coordinating session wrote this file from the run's
final report, because the astra role does not write report files.

## Outcome

- **The shipper.** A host whose boot stopped at `apply` no longer tries to stop a shipper unit that
  was never installed. One-shot shipping and its failure hold are unchanged.
- **A lost confirmation.** When a plain `down` loses the logout confirmation, it keeps the VM and
  exits 1 with one line. That line names:
  - the missing confirmation and the last departure step it received;
  - what `--force` risks: unshipped transcripts can be lost and the desk enrollment can remain;
  - the checks to run afterwards: `sminos machines` for the desk, and `devcloud vm ls` for tailnet
    nodes that no VM accounts for.

  A follow-up `down` that finds the host unreachable gives the same guidance.
- **`--force`.** An explicit `--force` now also deletes after an ambiguous disconnect. It goes
  through the existing deletion, which checks ownership and cleans up the tailnet node. It reports
  "deleted without departure confirmation" and doesn't claim the departure completed.
- **The spec.** The departure contract in the VM driver spec (§4.2) documents this behavior.

## Reproduction before the change

The original dropped confirmation didn't recur in two targeted trials. Both forced a failure at
`apply`, both delivered the ready line, and a plain `down` deleted both. The second trial removed
the executable, which matches the original failure more closely, and ran `down` within a minute of
the failed boot.

Two earlier injections didn't stop `apply`, because they targeted the wrong startup or executable
path. Those VMs served as healthy controls: both departed normally and were deleted.

For the first targeted trial, a scheduled serial-port snapshot preserved the host's lifecycle after
logout. It showed:
- admission closed, with nothing installed to disable;
- stopping the absent shipper unit failed, without stopping the departure;
- one-shot shipping succeeded;
- the host was not enrolled at the desk;
- logout succeeded and the ephemeral node left;
- no devcloud service needed stopping, and the lifecycle reached departed.

So the live evidence pointed to neither a service stop nor the departure's transient unit. The
original sequence fits logout completing before the flushed ready line reached the driver: the
first `down` lost its confirmation, and the retry found the host gone from the tailnet. The fix
takes the ticket's diagnostic alternative. It doesn't treat every disconnect as success.

## Regression evidence

`devcloud/tests/unit/test_driver_partial_departure.py` runs the real departure against a partially
booted host fixture, then cuts the returned transport just before the ready line. The host
completes its logout and the driver receives no confirmation. Four tests cover:
- skipping the absent unit while still shipping;
- a plain `down` that keeps the VM and says why;
- `--force` deleting after the lost confirmation;
- the unreachable follow-up and its cleanup guidance.

All four failed before the change and pass after it. `test_departure.py` passes 52 of 52, including
the existing holds.

## Live proof of the fixed code on GCE

One last leased throwaway booted the committed recipe with a deliberately failing executable.
`apply` failed as intended. A plain `devcloud vm down` exited 0 with `departed and deleted`. In its
transcript the departure:
- skipped the absent unit;
- still shipped;
- reported `not enrolled`;
- delivered `ready-to-logout`.

The host's departure module matched the committed file's SHA-256.

All five throwaways were created and deleted on 2026-10-22. No keep VM, adopt, scratch branch or
image bake was used. Afterwards:
- the provider's inventory held none of them;
- the Tailscale devices API listed none of them;
- `devcloud vm ls --json` reported no live throwaway;
- `sminos machines` listed none of them.

The desk directory was an event-cached copy, 18 minutes old. The departure transcripts confirm it
independently: both controls left the desk, and the three failed-`apply` hosts were never enrolled.
No machine or tailnet node was removed by hand.

## Review and CI

- doperpowers:review-code at the medium rung, on `7acef18a..5bd7a929`: no material findings.
- `ci-gate` on `5bd7a929`: green, 8/8 (run 39759118640).

## Friction

The run added two rows to friction tracker #304:
- A public SSH control master kept open across provisioning didn't survive, and later diagnostic
  commands hung. What worked was a bounded, scheduled snapshot of the lifecycle and journal to the
  GCE serial port before the departure.
- The root PR template still asks for a different target branch and a completed human review
  before submission. The task brief governed this PR, and the template was left unchanged.

## Residue

None. The live timing race is still unconfirmed, and this report says so instead of claiming it
was reproduced.
