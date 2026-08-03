// A leaf whose app-server dies mid-turn, followed by a leaf that must still run:
// the failure has to be reported, not waited on, and the semaphore slot it held
// has to come back.
export default async ({ agent }) => {
  const a = await agent("first", { label: "A" }).catch((err) => `A-failed: ${err.message}`);
  const b = await agent("second", { label: "B" });
  return { a, b };
};
