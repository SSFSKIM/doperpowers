export default async function run({ agent }) {
  // bare Promise.all — the semaphore must still cap live servers
  return Promise.all(Array.from({ length: 10 }, (_, i) => agent(`c${i}`, { label: `c${i}` })));
}
