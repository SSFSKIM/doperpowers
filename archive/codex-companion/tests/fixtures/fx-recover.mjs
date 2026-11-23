// One call that succeeds and one that dies. On a resume the successful call must
// be served from the journal, and the failed one must be re-run live — resume
// exists to recover a crashed run, not to replay its casualties.
export default async function run({ agent, parallel }) {
  const good = await agent("good", { label: "good" });
  const [risky] = await parallel([() => agent("risky", { label: "risky" })]);
  return { good, risky };
}
