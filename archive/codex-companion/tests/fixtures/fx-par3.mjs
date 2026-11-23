// Three concurrent leaf calls and nothing else: paired with a hanging scenario
// this holds three live mock app-servers open, so a cancel case can prove that
// ALL of them are killed, not just the first.
export default async function run({ agent, parallel }) {
  return parallel([
    () => agent("h1", { label: "h1" }),
    () => agent("h2", { label: "h2" }),
    () => agent("h3", { label: "h3" })
  ]);
}
