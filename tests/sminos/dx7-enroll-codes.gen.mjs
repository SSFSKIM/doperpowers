// Writes dx7-enroll-codes.json: DX7 enrollment codes built with the hub's own encoder, and damaged ones built by hand,
// each with the hub's own decoder's verdict ({note, text, ok, decoded?|error?}). enroll_parity.py pins sminos_hub's
// decoder to every one. The hub's module is MAWS apps/desk-hub/src/protocol/identity.ts, bundled first:
//
//   esbuild <MAWS>/apps/desk-hub/src/protocol/identity.ts --bundle --format=esm --platform=neutral --outfile=<dir>/identity.mjs
//   node dx7-enroll-codes.gen.mjs <dir>/identity.mjs > dx7-enroll-codes.json
const { encodeEnrollmentCode, decodeEnrollmentCode } = await import(new URL(process.argv[2], `file://${process.cwd()}/`).href);
const b64 = (s) => Buffer.from(s, 'utf8').toString('base64url');
const raw = (bytes) => Buffer.from(bytes).toString('base64url');
const KEY = raw(Array.from({ length: 32 }, (_, i) => i));
const base = { hub: 'https://desk.example.com', org: 'org-1', token: 'tok_' + raw(Array.from({ length: 32 }, (_, i) => 255 - i)), machine: 'SK-2.local', key: KEY };
const cases = [];
const enc = (note, fields) => cases.push({ note, text: encodeEnrollmentCode({ ...base, ...fields }) });
const lit = (note, text) => cases.push({ note, text });
const json = (note, obj) => lit(note, 'smns-enroll-v1.' + b64(JSON.stringify(obj)));
enc('a code as the browser builds it', {});
enc('the local runtime on 127.0.0.1', { hub: 'http://127.0.0.1:8747' });
enc('the local runtime on localhost', { hub: 'http://localhost:8747' });
enc('the local runtime on [::1]', { hub: 'http://[::1]:8747' });
enc('a one-character name', { machine: 'a' });
enc('a 63-character name', { machine: 'a'.repeat(63) });
enc('a name with dots, dashes, underscores', { machine: 'Mac_mini-2.lan' });
enc('a token and an org outside ASCII', { org: 'örg-€', token: 'tök€n-😀' });
enc('a hub with a path', { hub: 'https://desk.example.com/base' });
enc('an uppercase scheme', { hub: 'HTTPS://desk.example.com' });
json('fields in another order', { key: KEY, machine: 'm1', token: 't', org: 'o', hub: 'https://h.example' });
json('an extra field', { ...base, extra: [1, { x: null }] });
lit('a byte-order mark before the JSON', 'smns-enroll-v1.' + Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(JSON.stringify(base))]).toString('base64url'));
lit('whitespace around the JSON', 'smns-enroll-v1.' + b64(' \n' + JSON.stringify(base) + '\t '));
lit('a duplicated field, the last kept', 'smns-enroll-v1.' + b64(JSON.stringify(base).slice(0, -1) + ',"machine":"later"}'));
// negatives
lit('another prefix', 'smns-enroll-v2.' + b64(JSON.stringify(base)));
lit('no prefix', b64(JSON.stringify(base)));
lit('an empty body', 'smns-enroll-v1.');
{
  const body = b64(JSON.stringify(base) + 'x');
  lit('padding on the body', 'smns-enroll-v1.' + body + '='.repeat((4 - (body.length % 4)) % 4));
}
lit('standard base64 characters in the body', 'smns-enroll-v1.' + Buffer.from(JSON.stringify(base) + '~~~').toString('base64'));
{
  const good = b64(JSON.stringify(base) + ' ');
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  const bump = alphabet[alphabet.indexOf(good.at(-1)) + 1];
  lit('spare bits set in the last character', 'smns-enroll-v1.' + good.slice(0, -1) + bump);
}
{
  const body = b64(JSON.stringify(base));
  lit('an impossible length', 'smns-enroll-v1.' + body + 'A'.repeat(((5 - (body.length % 4)) % 4) || 4));
}
lit('a body that is not UTF-8', 'smns-enroll-v1.' + raw([0x7b, 0xff, 0x7d]));
lit('a body that is not JSON', 'smns-enroll-v1.' + b64('hub=https://x'));
lit('NaN in the JSON', 'smns-enroll-v1.' + b64(JSON.stringify(base).slice(0, -1) + ',"n":NaN}'));
json('a JSON array', [base]);
json('a JSON string', 'smns');
json('JSON null', null);
json('a JSON number', 7);
for (const f of ['hub', 'org', 'token', 'machine', 'key']) {
  const { [f]: _, ...rest } = base;
  json(`no ${f}`, rest);
  json(`an empty ${f}`, { ...base, [f]: '' });
  json(`a ${f} that is not a string`, { ...base, [f]: 7 });
}
json('a hub that is not a URL', { ...base, hub: 'desk.example.com' });
json('a hub of another scheme', { ...base, hub: 'ftp://desk.example.com' });
json('a hub over http off this machine', { ...base, hub: 'http://desk.example.com' });
json('a hub over http on another loopback address', { ...base, hub: 'http://127.0.0.2:8747' });
json('a hub with no host', { ...base, hub: 'https://' });
for (const m of ['hub', 'HUB', 'Legacy', '-x', '.x', 'a b', 'x/y', 'x\n', 'a'.repeat(64), 'é', 'x:y']) json(`the machine name ${JSON.stringify(m)}`, { ...base, machine: m });
json('a key of 31 bytes', { ...base, key: raw(Array(31).fill(1)) });
json('a key of 33 bytes', { ...base, key: raw(Array(33).fill(1)) });
json('a padded key', { ...base, key: KEY + '=' });
json('a key in standard base64', { ...base, key: Buffer.from(Array(32).fill(0xfb)).toString('base64').replace(/=+$/, '') });
json('a key with spare bits set', { ...base, key: KEY.slice(0, -1) + 'x' });
const out = cases.map(({ note, text }) => {
  try {
    return { note, text, ok: true, decoded: decodeEnrollmentCode(text) };
  } catch (e) {
    return { note, text, ok: false, error: e.message };
  }
});
process.stdout.write(JSON.stringify(out, null, 1) + '\n');
