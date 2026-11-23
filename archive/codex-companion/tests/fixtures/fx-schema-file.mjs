// The schema is read from a FILE the args merely point at, so it can change
// while `--args` stays byte-identical. Args ride the run fingerprint, so a
// schema handed in through args would refuse the resume outright and prove
// nothing about the cache KEY — which is what this fixture is for.
import fs from "node:fs";

export default async function run({ agent, args }) {
  const schema = JSON.parse(fs.readFileSync(args.schemaPath, "utf8"));
  return agent("emit the object", { label: "schema", schema });
}
