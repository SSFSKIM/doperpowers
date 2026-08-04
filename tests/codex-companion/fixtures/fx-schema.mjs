const S = { type: "object", required: ["ok"], properties: { ok: { type: "boolean" } } };
export default async function run({ agent }) {
  return agent("give me json", { label: "js", schema: S });
}
