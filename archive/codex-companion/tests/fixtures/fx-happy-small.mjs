// CLI e2e happy path: one solo agent plus a two-thunk parallel — exactly three
// leaf calls, so the verb's reported `agents` is a fixed 3.
export default async function run({ agent, parallel, log, args }) {
  log("small workflow starting");
  const one = await agent("solo", { label: "solo" });
  const par = await parallel([
    () => agent("p1", { label: "p1" }),
    () => agent("p2", { label: "p2" })
  ]);
  return { one, par, n: args.n };
}
