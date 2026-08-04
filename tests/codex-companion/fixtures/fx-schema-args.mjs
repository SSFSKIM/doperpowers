// The schema arrives through args, so one fixture can be run under two schemas
// that differ only in bytes the old cache key never looked at.
export default async function run({ agent, args }) {
  return agent("emit the object", { label: "schema", schema: args.schema });
}
