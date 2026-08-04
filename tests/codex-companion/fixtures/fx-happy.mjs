export default async function run({ agent, parallel, pipeline, log, args }) {
  log("starting");
  const one = await agent("solo", { label: "solo" });
  const par = await parallel([
    () => agent("p1", { label: "p1" }),
    () => agent("boom", { label: "boom" }),     // scenario kills this one twice
    () => agent("p3", { label: "p3" }),
  ]);
  const piped = await pipeline([10, 20],
    (x) => agent(`stage1-${x}`, { label: `s1-${x}` }),
    (prev, orig, i) => (orig === 20 ? (() => { throw new Error("drop"); })() : `${prev}|${orig}|${i}`));
  return { one, par, piped, n: args.n };
}
