// Resume shape: A, then parallel(B slow, C fast), then D.
//
// The interesting property is the HOLE: B is still in flight when C finishes, so
// a run killed there journals `finished` A, `finished` C and a `started`-only B.
// Resuming must serve A and C from the journal and re-run B (and then D) live —
// which only works if the cache is keyed by call identity, not by position.
//
// The mock app-server consumes its scenario in GLOBAL turn/start order, so B and
// C would otherwise race for the "slow" slot and the hole could land on either.
// When the test drops a `stagger` marker in the mock dir, C waits until B's
// turn/start has actually taken its slot (the mock's counter file) before
// issuing its own — deterministic without a sleep. On a resume the marker is
// absent: C is served from cache and issues no turn at all, so waiting on the
// counter there would deadlock.
import fs from "node:fs";
import path from "node:path";

const MOCK = process.env.CODEX_MOCK_DIR ?? null;

function counter() {
  try { return Number(fs.readFileSync(path.join(MOCK, "counter"), "utf8")) || 0; }
  catch { return 0; }
}

async function waitForSlot(n, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (counter() < n && Date.now() < deadline) {
    await new Promise((res) => setTimeout(res, 20));
  }
}

export default async function run({ agent, parallel }) {
  const a = await agent("A", { label: "A" });
  const [b, c] = await parallel([
    () => agent("B", { label: "B" }),
    async () => {
      if (MOCK && fs.existsSync(path.join(MOCK, "stagger"))) await waitForSlot(2);
      return agent("C", { label: "C" });
    }
  ]);
  const d = await agent("D", { label: "D" });
  return { a, b, c, d };
}
