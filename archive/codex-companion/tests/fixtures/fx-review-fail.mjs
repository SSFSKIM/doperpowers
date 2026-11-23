// A review whose turn completes UNSUCCESSFULLY still carries review text; the
// status gate has to reject it before a panel treats it as a finding.
export default async function run({ review, parallel }) {
  return parallel([() => review({ base: "main", label: "sweep" })]);
}
