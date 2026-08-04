// One agent behind `parallel` — the turn completes with a FAILED status and a
// plausible-looking final message; the call must reject and be absorbed to null.
export default async function run({ agent, parallel }) {
  return parallel([() => agent("status", { label: "st" })]);
}
