// How many calls this script makes is decided by args. The leaf cache keys on
// the call payload plus which occurrence of that identity it is within THIS
// run, so dropping n from 2 to 1 would hand a later logical call the earlier
// one's journaled result — unless the args are part of the run identity.
export default async function run({ agent, args }) {
  const out = [];
  for (let i = 0; i < args.n; i++) out.push(await agent("same", { label: "dup" }));
  return out;
}
