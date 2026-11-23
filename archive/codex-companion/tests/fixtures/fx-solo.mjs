// One leaf call: the cheapest possible run, for cases that launch many
// workflows at once and only care about the job records they leave behind.
export default async function run({ agent }) {
  return { one: await agent("solo", { label: "solo" }) };
}
