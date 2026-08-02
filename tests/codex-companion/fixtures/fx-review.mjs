// The review hook, fully specified: an explicit base, a lens and an effort that
// have to reach the worker's own app-server as `-c` overrides.
export default async function run({ review }) {
  return review({
    base: "main",
    lens: "watch the auth paths.",
    effort: "xhigh",
    model: "gpt-5.6-sol",
    label: "sweep"
  });
}
