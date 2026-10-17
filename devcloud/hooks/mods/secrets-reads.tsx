/**
 * What to read in a shell command where the guard left a handle: for each
 * kind of source, a command that prints exactly the value's bytes (no newline
 * added, the file's own escaping undone), and the notice that names it. Pure;
 * each command is run against real files by tests/mods/shell-exec.ts.
 */

/** Where a known value comes from, enough for a command to read it. Paths are from $HOME. */
export type Read =
  | { kind: 'store'; path: string }
  | { kind: 'json'; path: string; keys: readonly string[] }
  | { kind: 'gh'; host: string; user?: string }
  | { kind: 'toml'; path: string; table: string; index?: number; key: string }
  | { kind: 'pgpass'; path: string; match: string[]; nth: number }
  | { kind: 'netrc'; path: string; machine: string; nth: number }
  | { kind: 'git-credentials'; path: string; id: string; nth: number }
  | { kind: 'npmrc'; path: string; key: string; nth: number }

/** The step that turns a value read in a command into a handle's encoding. */
export const ENCODE: Record<string, string> = {
  b64: "base64 | tr -d '\\n'",
  b64np: "base64 | tr -d '\\n='",
  b64u: "base64 | tr -d '\\n=' | tr '+/' '-_'",
  b64up: "base64 | tr -d '\\n' | tr '+/' '-_'",
  hex: "xxd -p | tr -d '\\n'",
  HEX: "xxd -p | tr -d '\\n' | tr a-f A-F",
  url: `python3 -c 'import sys,urllib.parse; sys.stdout.write(urllib.parse.quote(sys.stdin.read(), safe="!*()\\x27"))'`,
  json: `python3 -c 'import sys,json; sys.stdout.write(json.dumps(sys.stdin.read(), ensure_ascii=False)[1:-1])'`,
  pgpass: "sed 's/[\\\\:]/\\\\&/g'",
}

// An argument as the shell will read it back: as it is when plain, else
// single-quoted.
export const quote = (arg: string) => (/^[A-Za-z0-9_./@:%+=,-]+$/.test(arg) ? arg : `'${arg.replace(/'/g, `'\\''`)}'`)
const home = (path: string) => `~/${/^[A-Za-z0-9_./@:%+=,-]+$/.test(path) ? path : quote(path)}`

// The Python each file kind is read with, written for a single-quoted shell
// string (no `'` inside); each prints the value and nothing else.
const PY = {
  json: String.raw`import json,sys,functools;a=sys.argv;sys.stdout.write(functools.reduce(lambda v,k:v[int(k)] if isinstance(v,list) else v[k],a[2:],json.load(open(a[1]))))`,
  toml: String.raw`import sys,tomllib,functools;a=sys.argv;t=functools.reduce(lambda t,k:t[k],[k for k in a[2].split(".") if k],tomllib.load(open(a[1],"rb")));t=t[int(a[3])] if a[3] else t;sys.stdout.write(t[a[4]])`,
  pgpass: String.raw`import re,sys;a=sys.argv;m=[p for p in (re.split(r"(?<!\\):",l.rstrip("\n")) for l in open(a[1]) if l.strip() and not l.startswith("#")) if len(p)==5 and p[:4]==a[2:6]];sys.stdout.write(re.sub(r"\\(.)",r"\1",m[int(a[6])][4]))`,
  // Tokenized as secrets-sources reads .netrc (curl's rules: `\n`, `\r`, `\t`
  // in a quoted word), not as Python's netrc module does.
  netrc: String.raw`import re,sys;a=sys.argv;w=[re.sub(r"\\([\s\S]?)",lambda e:{"n":"\n","r":"\r","t":"\t"}.get(e[1],e[1]),q) if u=="" else u for q,u in re.findall(r"\"((?:\\[\s\S]?|[^\"\\])*)\"?|(\S+)",open(a[1]).read())];m="";it=iter(w);o=[(m,v) for x in it if (m:=(next(it,"") if x=="machine" else "default" if x=="default" else m)) is not None and (v:=(next(it,None) if x=="password" else [next(it,None),None][1] if x in ("login","account") else None)) is not None];sys.stdout.write([v for k,v in o if k==a[2]][int(a[3])])`,
  gitCredentials: String.raw`import sys,urllib.parse as u;a=sys.argv;m=[s for s in (u.urlsplit(l.strip()) for l in open(a[1])) if s.password is not None and u.unquote(s.username or "")+"@"+s.netloc.rpartition("@")[2]+s.path==a[2]];sys.stdout.write(u.unquote(m[int(a[3])].password))`,
  npmrc: String.raw`import sys;a=sys.argv;m=[l.split("=",1)[1].strip() for l in open(a[1]) if "=" in l and l.split("=",1)[0].strip()==a[2]];v=m[int(a[3])];sys.stdout.write(v[1:-1] if len(v)>1 and v[0]==v[-1] and v[0] in "\x22\x27" else v)`,
}

// A jq path to a JSON field's keys, or undefined where one would need quoting.
const jqPath = (keys: readonly string[]) =>
  keys.some((k) => k.includes("'"))
    ? undefined
    : keys.map((k) => (/^\d+$/.test(k) ? `[${k}]` : /^[A-Za-z_][A-Za-z0-9_]*$/.test(k) ? `.${k}` : `[${JSON.stringify(k)}]`)).join('').replace(/^\[/, '.[')

/** A command that prints exactly the value `read` names. */
export function readCommand(read: Read): string {
  switch (read.kind) {
    case 'store':
      // The store drops one trailing newline on read; so does this.
      return `perl -pe 'chomp if eof' ${home(read.path)}`
    case 'json': {
      const path = jqPath(read.keys)
      return path ? `jq -j '${path}' ${home(read.path)}` : `python3 -c '${PY.json}' ${home(read.path)} ${read.keys.map(quote).join(' ')}`
    }
    case 'gh':
      return `gh auth token --hostname ${quote(read.host)}${read.user ? ` --user ${quote(read.user)}` : ''} | tr -d '\\n'`
    case 'toml':
      return `python3 -c '${PY.toml}' ${home(read.path)} ${quote(read.table) || "''"} ${read.index ?? "''"} ${quote(read.key)}`
    case 'pgpass':
      return `python3 -c '${PY.pgpass}' ${home(read.path)} ${read.match.map((f) => quote(f)).join(' ')} ${read.nth}`
    case 'netrc':
      return `python3 -c '${PY.netrc}' ${home(read.path)} ${quote(read.machine)} ${read.nth}`
    case 'git-credentials':
      return `python3 -c '${PY.gitCredentials}' ${home(read.path)} ${quote(read.id)} ${read.nth}`
    case 'npmrc':
      return `python3 -c '${PY.npmrc}' ${home(read.path)} ${quote(read.key)} ${read.nth}`
  }
}

// What the read undoes of how the file writes the value.
const DECODES: Partial<Record<Read['kind'], string>> = {
  pgpass: "it undoes .pgpass's backslash escapes",
  'git-credentials': 'it URL-decodes the password',
  netrc: 'it decodes netrc quoting',
  toml: 'tomllib decodes TOML strings',
  npmrc: "it drops .npmrc's quotes",
}

/**
 * The notice's read for a handle: `"$(…)"` of the exact read (piped through
 * the handle's encoding), or, for bytes that end in a newline `"$(…)"` would
 * drop, the read to pipe or pass as a file. `endsInNewline` is about the
 * bytes the handle stands for (its encoding applied).
 */
export function readNotice(read: Read | undefined, enc: string, endsInNewline: boolean): string {
  if (!read) return 'read its source in the command'
  const encode = enc ? ENCODE[enc] : undefined
  const decodes = DECODES[read.kind] ? ` (${DECODES[read.kind]})` : ''
  const full = encode ? `${readCommand(read)} | ${encode}` : readCommand(read)
  if (endsInNewline) return `pipe it, as its value ends in a newline that "$(…)" would drop: ${full} | <command>, or pass it as a file: <(${full})${decodes}`
  if (!encode && read.kind === 'store') return `use "$(cat ${home(read.path)})" in the command`
  if (!encode && read.kind === 'gh') return `use "$(gh auth token --hostname ${quote(read.host)}${read.user ? ` --user ${quote(read.user)}` : ''})" in the command`
  return `use "$(${full})" in the command${decodes}`
}

/** The notice's read for a pattern handle, which has no source on disk. */
export const PATTERN_READ =
  'it has no source on disk, so it stays unrestored in shell commands: to use it, write it with a file tool (file tools restore it) to a temporary file, then use "$(cat <that file>)" in the command'
