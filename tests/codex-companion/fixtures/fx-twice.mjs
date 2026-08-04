// Two byte-identical calls. Content-keyed caching alone would collapse them into
// one journal entry; the per-run occurrence counter keeps them distinct, which is
// what a resume has to replay in order.
export default async function run({ agent }) {
  const a = await agent("same", { label: "dup" });
  const b = await agent("same", { label: "dup" });
  return [a, b];
}
