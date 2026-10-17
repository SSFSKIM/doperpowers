// The secrets guard's detector (hooks/mods/secrets-detect.tsx) run over a
// directory tree, or over stdin when the argument is `-`: one line per finding,
// `<path>\t<kind>\t<offset>`, never the text found. Files that hold a NUL in
// their first 8 KiB (binaries) and files past 8 MiB are skipped.
import { lstatSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { detect } from "../hooks/mods/secrets-detect.tsx";

const MAX = 8 << 20;
let files = 0;

function scan(label: string, bytes: Buffer) {
  if (bytes.subarray(0, 8192).includes(0)) return;
  files++;
  for (const span of detect(bytes.toString("utf8"))) console.log(`${label}\t${span.kind}\t${span.start}`);
}

function walk(dir: string) {
  let names: string[];
  try { names = readdirSync(dir); } catch { return; }
  for (const name of names) {
    const path = join(dir, name);
    let stat;
    try { stat = lstatSync(path); } catch { continue; }
    if (stat.isDirectory()) walk(path);
    else if (stat.isFile() && stat.size <= MAX && stat.size > 0) {
      try { scan(path, readFileSync(path)); } catch { /* unreadable: skipped */ }
    }
  }
}

const target = process.argv[2];
if (!target) { console.error("usage: bun scan-secrets.ts <dir>|-"); process.exit(2); }
if (target === "-") scan("<stdin>", readFileSync(0));
else walk(target);
console.error(`scanned ${files} text files`);
