// One agent pointed at ANOTHER repository through the documented per-call cwd.
export default async function run({ agent, args }) {
  return agent("inspect the other repo", { label: "other", cwd: args.cwd });
}
