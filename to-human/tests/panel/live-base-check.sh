#!/usr/bin/env bash
# The panel's base in a browser (playwright-cli, headless Chromium): a hand-written panel served by a real server
# in a throwaway configuration directory on a free port. It checks the notes' placement at 1280 and 600 wide, the
# count and the jump, a check surviving a reload and another browser, a look reported only from a visible tab,
# one reload on a publish keeping the scroll, the Korean words, and what a page may do (an inline script, an
# external image, a refresh meta and a dns-prefetch link: none runs, shows, moves the page or reaches another
# host; every request is intercepted, so none leaves the machine).
#
# Run by hand: bash to-human/tests/panel/live-base-check.sh   (needs playwright-cli and python3; no model calls)
# KEEP=1 leaves the directory (screenshots in it) for a look.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
server="$here/../../panel/server.py"
command -v playwright-cli >/dev/null || { echo "live-base-check needs playwright-cli" >&2; exit 1; }

work="$(mktemp -d "${TMPDIR:-/tmp}/panel-base-check.XXXXXX")"
export CLAUDE_CONFIG_DIR="$work/config"
PANEL_PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
export PANEL_PORT
unset PANEL_REACH PANEL_LOCALE
pw_session="panel-base-check-$$"
origin="http://127.0.0.1:$PANEL_PORT"
panels="$CLAUDE_CONFIG_DIR/to-human/panels"

cleanup() {
  playwright-cli -s="$pw_session" close >/dev/null 2>&1 || true
  if [ -f "$panels/server.json" ]; then
    kill "$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["pid"])' "$panels/server.json")" 2>/dev/null || true
  fi
  if [ -n "${KEEP:-}" ]; then echo "kept: $work"; else rm -rf "$work"; fi
}
trap cleanup EXIT

ok() { echo "ok - $*"; }
fail() { echo "FAIL - $*" >&2; exit 1; }

open_panel() { python3 "$server" open-panel --session "$1" ${2:+--locale "$2"}; }
publish() { python3 "$server" publish --session "$1"; }
field() { python3 -c 'import json, sys; v = json.loads(sys.argv[1])[sys.argv[2]]; print(json.dumps(v) if not isinstance(v, str) else v)' "$1" "$2"; }
state() { python3 -c 'import json, sys; v = json.load(open(sys.argv[1]))[sys.argv[2]]; print(json.dumps(v))' "$panels/$1/state.json" "$2"; }

# A step: a Playwright function read from stdin, with __ORIGIN__, __PANEL__ and __WORK__ put in; it throws on a
# failed check.
step() {
  local name="$1" addr="$2" file="$work/$1.js"
  sed -e "s#__ORIGIN__#$origin#g" -e "s#__PANEL__#$addr#g" -e "s#__WORK__#$work#g" > "$file"
  local out
  if ! out="$(playwright-cli -s="$pw_session" run-code --filename="$file" 2>&1)"; then
    echo "$out" >&2
    fail "$name"
  fi
}

# The page every English check reads: long enough to scroll, two notes in paragraphs, one in a list item.
draft_en() {
  python3 - "$1" "${2:-}" <<'PY'
import sys
path, extra = sys.argv[1], sys.argv[2]
filler = "".join("<p>Filler paragraph %d, so the page is long enough to scroll and the notes stand at different "
                 "heights. It says nothing that matters.</p>\n" % i for i in range(1, 17))
body = f"""<h1>Two ways to serve the panels</h1>
<p class="meta">Session 0000aaaa · an example</p>
<section class="ask"><p class="label">Needs you</p><h2>Pick A or B</h2><p>The session asks in the dialog.</p></section>
<h2>The options</h2>
<p>Option A runs <mark data-note="u1-1">one server for every session on a machine</mark>, on a fixed port.</p>
<aside class="note" id="u1-1" data-label="Changed by your answer">Was: one server per session.</aside>
{filler}
<ul><li>Option B keeps <mark data-note="u1-2">a server inside each session</mark>.
<aside class="note" id="u1-2">Was: not considered.</aside></li>
<li>Either way the page is read-only.</li></ul>
{filler}
{extra}
"""
open(path, "w").write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Two ways</title>\n'
    '<link rel="stylesheet" href="/base/panel.css">\n<script src="/base/panel.js" defer></script>\n'
    '</head>\n<body>\n' + body + '</body>\n</html>\n')
PY
}

# ------------------------------------------------------------------ an English panel

sid=0000aaaa-1111-2222-3333-444444444444
short=${sid:0:8}
o="$(open_panel "$sid")"
draft="$(field "$o" draft)"
addr="$(field "$o" address)"
draft_en "$draft"
written="$(field "$(publish "$sid")" written)"
[ "$written" != null ] || fail "the first publish"
ok "published $addr"
playwright-cli -s="$pw_session" open about:blank >/dev/null

# A look from a hidden tab is not reported; the same tab becoming visible reports it.
step hidden-look "$addr" <<'JS'
async page => {
  const ctx = await page.context().browser().newContext();
  const p = await ctx.newPage();
  await p.addInitScript(() => {
    let state = 'hidden';
    Object.defineProperty(document, 'visibilityState', { get: () => state, configurable: true });
    Object.defineProperty(document, 'hidden', { get: () => state === 'hidden', configurable: true });
    window.__show = () => { state = 'visible'; document.dispatchEvent(new Event('visibilitychange')); };
  });
  await p.goto('__PANEL__');
  await p.waitForTimeout(1500);
  await ctx.close();
}
JS
[ "$(state "$short" seen)" = null ] || fail "a hidden tab reported a look"
ok "a hidden tab reports no look"

step shown-look "$addr" <<'JS'
async page => {
  const ctx = await page.context().browser().newContext();
  const p = await ctx.newPage();
  await p.addInitScript(() => {
    let state = 'hidden';
    Object.defineProperty(document, 'visibilityState', { get: () => state, configurable: true });
    Object.defineProperty(document, 'hidden', { get: () => state === 'hidden', configurable: true });
    window.__show = () => { state = 'visible'; document.dispatchEvent(new Event('visibilitychange')); };
  });
  await p.goto('__PANEL__');
  await p.waitForTimeout(500);
  await p.evaluate(() => window.__show());
  await p.waitForTimeout(1000);
  await ctx.close();
}
JS
[ "$(state "$short" seen)" = "$written" ] || fail "a tab that became visible did not report its look ($(state "$short" seen))"
ok "a tab that becomes visible reports the look of the publication it shows"

# Placement at 1280: in the margin, at the height of the anchor, notes not overlapping.
step wide "$addr" <<'JS'
async page => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('__PANEL__');
  await page.waitForSelector('aside.note.is-open');
  const r = await page.evaluate(() => {
    const out = { wide: document.documentElement.classList.contains('panel-wide'), notes: [] };
    for (const id of ['u1-1', 'u1-2']) {
      const n = document.getElementById(id).getBoundingClientRect();
      const m = document.querySelector(`mark[data-note="${id}"]`);
      const mr = m.getBoundingClientRect();
      const block = m.closest('p, li').getBoundingClientRect();
      out.notes.push({ id, dy: n.top - mr.top, left: n.left, blockRight: block.right, marked: m.classList.contains('is-open'),
                       inMargin: document.getElementById(id).parentElement.className });
    }
    out.bar = document.querySelector('.panel-notebar')?.textContent;
    out.check = document.querySelector('#u1-1 .check')?.getAttribute('aria-label');
    out.label = document.querySelector('#u1-1 .what')?.textContent;
    return out;
  });
  const bad = [];
  if (!r.wide) bad.push('not in the wide layout');
  for (const n of r.notes) {
    if (Math.abs(n.dy) > 12) bad.push(`${n.id} stands ${n.dy}px from its anchor`);
    if (n.left < n.blockRight) bad.push(`${n.id} is not in the margin`);
    if (!n.marked) bad.push(`${n.id}'s phrase is not highlighted`);
    if (n.inMargin !== 'panel-margin') bad.push(`${n.id} is not in the margin layer`);
  }
  if (!/^2 notes on what changed/.test(r.bar || '')) bad.push(`the count reads ${r.bar}`);
  if (!/^Mark as read/.test(r.check || '')) bad.push(`the check reads ${r.check}`);
  if (r.label !== 'Changed by your answer') bad.push(`the label reads ${r.label}`);
  await page.screenshot({ path: '__WORK__/wide.png', fullPage: false });
  if (bad.length) throw new Error(bad.join('; '));
}
JS
ok "1280 wide: each note in the margin at its anchor's height, its phrase highlighted, the count reads 2"

# Placement at 600: under the anchor's block.
step narrow "$addr" <<'JS'
async page => {
  await page.setViewportSize({ width: 600, height: 900 });
  await page.waitForTimeout(300);
  const r = await page.evaluate(() => {
    const out = { wide: document.documentElement.classList.contains('panel-wide'), notes: [] };
    for (const id of ['u1-1', 'u1-2']) {
      const n = document.getElementById(id);
      const m = document.querySelector(`mark[data-note="${id}"]`);
      const block = m.closest('li') || m.closest('p');
      const nr = n.getBoundingClientRect(), br = block.getBoundingClientRect();
      out.notes.push({ id, below: nr.top >= br.bottom - 1 || block.contains(n), near: nr.top - br.bottom,
                       inside: block.contains(n), after: n.previousElementSibling === block,
                       left: nr.left, width: nr.width, page: document.body.clientWidth });
    }
    return out;
  });
  const bad = [];
  if (r.wide) bad.push('still in the wide layout');
  for (const n of r.notes) {
    if (!(n.after || n.inside)) bad.push(`${n.id} is not under its anchor's block`);
    if (n.near > 40) bad.push(`${n.id} stands ${n.near}px below its block`);
    if (n.left < 0 || n.width > n.page) bad.push(`${n.id} overflows the window`);
  }
  await page.screenshot({ path: '__WORK__/narrow.png', fullPage: false });
  if (bad.length) throw new Error(bad.join('; '));
}
JS
ok "600 wide: each note under its anchor's block"

# The jump to the next note, then a check.
step jump-and-check "$addr" <<'JS'
async page => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.waitForTimeout(300);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.click('.panel-notebar button');
  await page.waitForTimeout(400);
  const seen1 = await page.evaluate(() => {
    const r = document.querySelector('mark[data-note="u1-1"]').getBoundingClientRect();
    return r.top >= 0 && r.bottom <= innerHeight;
  });
  if (!seen1) throw new Error('the jump did not bring the first note into view');
  await page.click('.panel-notebar button');
  await page.waitForTimeout(400);
  const seen2 = await page.evaluate(() => {
    const r = document.querySelector('mark[data-note="u1-2"]').getBoundingClientRect();
    return r.top >= 0 && r.bottom <= innerHeight;
  });
  if (!seen2) throw new Error('the second jump did not bring the next note into view');
  await page.click('#u1-1 .check');
  await page.waitForTimeout(500);
  const r = await page.evaluate(() => ({
    shown: getComputedStyle(document.getElementById('u1-1')).display,
    marked: document.querySelector('mark[data-note="u1-1"]').classList.contains('is-open'),
    bar: document.querySelector('.panel-notebar').textContent,
  }));
  if (r.shown !== 'none' || r.marked) throw new Error('the checked note or its highlight still shows');
  if (!/^1 note on what changed/.test(r.bar)) throw new Error(`the count reads ${r.bar}`);
}
JS
[ "$(state "$short" checked)" = '["u1-1"]' ] || fail "state.json does not list the check ($(state "$short" checked))"
ok "the jump goes to each open note in turn; a check removes the note and its highlight; state.json lists it"

step check-survives "$addr" <<'JS'
async page => {
  const hidden = (p) => p.evaluate(() => getComputedStyle(document.getElementById('u1-1')).display === 'none'
    && !document.querySelector('mark[data-note="u1-1"]').classList.contains('is-open')
    && getComputedStyle(document.getElementById('u1-2')).display !== 'none');
  await page.reload();
  await page.waitForSelector('#u1-2.is-open');
  if (!(await hidden(page))) throw new Error('after a reload the checked note shows');
  const ctx = await page.context().browser().newContext();
  const p = await ctx.newPage();
  await p.setViewportSize({ width: 1280, height: 900 });
  await p.goto('__PANEL__');
  await p.waitForSelector('#u1-2.is-open');
  const ok = await hidden(p);
  await ctx.close();
  if (!ok) throw new Error('in another browser the checked note shows');
}
JS
ok "the check holds after a reload and in another browser"

# One reload on a publish, keeping the scroll; none while the draft is edited.
step before-publish "$addr" <<'JS'
async page => {
  await page.setViewportSize({ width: 1280, height: 900 });
  const y = await page.evaluate(() => { window.scrollTo(0, 700); window.__marker = 'before'; return window.scrollY; });
  if (y !== 700) throw new Error(`the page scrolled to ${y}, not 700`);
}
JS
o2="$(open_panel "$sid")"
[ "$(field "$o2" update)" = 2 ] || fail "the second open-panel's update"
draft_en "$draft" '<p>New: <mark data-note="u2-1">a third option</mark> appears.</p><aside class="note" id="u2-1">New since you read it.</aside>'
step no-reload-while-drafting "$addr" <<'JS'
async page => {
  await page.waitForTimeout(4500);
  const m = await page.evaluate(() => window.__marker);
  if (m !== 'before') throw new Error('the page reloaded while the draft was edited');
}
JS
ok "the open page does not change while the draft is edited"
publish "$sid" >/dev/null
step reload-on-publish "$addr" <<'JS'
async page => {
  const t0 = Date.now();
  await page.waitForFunction(() => window.__marker === undefined && document.readyState === 'complete', null, { timeout: 5000 });
  await page.waitForSelector('#u2-1.is-open', { timeout: 3000 });
  const dt = Date.now() - t0;
  const y = await page.evaluate(() => window.scrollY);
  if (Math.abs(y - 700) > 4) throw new Error(`the scroll is ${y}, not 700`);
  await page.evaluate(() => { window.__marker = 'after'; });
  await page.waitForTimeout(4500);
  const m = await page.evaluate(() => window.__marker);
  if (m !== 'after') throw new Error('the page reloaded a second time');
  return dt;
}
JS
ok "a publish reloads the open page once, within 5 s, at the scroll it had"

# ------------------------------------------------------------------ a Korean panel

ko=0000bbbb-1111-2222-3333-444444444444
ok_ko="$(open_panel "$ko" ko)"
python3 - "$(field "$ok_ko" draft)" <<'PY'
import sys
open(sys.argv[1], "w").write('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<title>패널</title>\n'
    '<link rel="stylesheet" href="/base/panel.css">\n<script src="/base/panel.js" defer></script>\n</head>\n<body>\n'
    '<h1>두 가지 방법</h1>\n<p>서버는 <mark data-note="u1-1">기계마다 하나</mark>입니다.</p>\n'
    '<aside class="note" id="u1-1">세션마다 하나였습니다.</aside>\n</body>\n</html>\n')
PY
publish "$ko" >/dev/null
step korean "$(field "$ok_ko" address)" <<'JS'
async page => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('__PANEL__');
  await page.waitForSelector('aside.note.is-open');
  const r = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    bar: document.querySelector('.panel-notebar').textContent,
    check: document.querySelector('#u1-1 .check').getAttribute('aria-label'),
    breaks: getComputedStyle(document.body).wordBreak,
  }));
  await page.screenshot({ path: '__WORK__/korean.png' });
  const bad = [];
  if (r.lang !== 'ko') bad.push(`lang ${r.lang}`);
  if (!r.bar.startsWith('바뀐 내용 메모 1개')) bad.push(`the count reads ${r.bar}`);
  if (!r.check.startsWith('읽음으로 표시')) bad.push(`the check reads ${r.check}`);
  if (r.breaks !== 'keep-all') bad.push(`word-break ${r.breaks}`);
  if (bad.length) throw new Error(bad.join('; '));
}
JS
ok "Korean: lang ko, the count and the check in Korean, words kept whole"

# ------------------------------------------------------------------ what a page may do

bad=0000cccc-1111-2222-3333-444444444444
ob="$(open_panel "$bad")"
python3 - "$(field "$ob" draft)" <<'PY'
import sys
open(sys.argv[1], "w").write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Plain</title>\n'
    '<meta http-equiv="refresh" content="0;url=https://example.com/">\n'
    '<link rel="dns-prefetch" href="//example.com">\n'
    '<link rel="stylesheet" href="/base/panel.css">\n<script src="/base/panel.js" defer></script>\n</head>\n<body>\n'
    '<!--><meta http-equiv="refresh" content="1;url=https://example.org/"><!-- -->\n'
    '<script>window.__ran = true; document.title = "pwned";</script>\n'
    '<p onclick="window.__ran = true">A page that tries.</p>\n'
    '<img id="ext" src="https://example.com/pixel.png" alt="">\n'
    '<div style="background: url(https://example.net/bg.png)">styled</div>\n'
    '</body>\n</html>\n')
PY
pb="$(publish "$bad")"
[ "$(field "$pb" removed)" = '["meta http-equiv", "link"]' ] || fail "publish removed $(field "$pb" removed)"
curl -s "$(field "$ob" address)" | grep -Eqi 'http-equiv|dns-prefetch' && fail "the served page holds a cut tag"
step what-a-page-may-do "$(field "$ob" address)" <<'JS'
async page => {
  const ctx = await page.context().browser().newContext();
  const foreign = [];
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.origin === '__ORIGIN__') return route.continue();
    foreign.push(u.href);
    return route.abort();
  });
  const p = await ctx.newPage();
  await p.goto('__PANEL__');
  await p.waitForTimeout(3000);
  await p.click('p').catch(() => {});
  const r = await p.evaluate(() => ({ ran: window.__ran === true, title: document.title,
                                      img: document.getElementById('ext').naturalWidth }));
  const url = p.url();
  await ctx.close();
  const bad = [];
  if (r.ran) bad.push('a script of the page ran');
  if (r.title !== 'Plain') bad.push(`the title became ${r.title}`);
  if (r.img !== 0) bad.push('the external image loaded');
  if (url !== '__PANEL__') bad.push(`the page went to ${url}`);
  if (foreign.length) bad.push(`requests to another host: ${foreign.join(', ')}`);
  if (bad.length) throw new Error(bad.join('; '));
}
JS
ok "a page's own script, external image and refresh do nothing, and no request leaves for another host"

# A draft that leaves a tag open where the server's script goes: an open meta at the end would take the
# script's quotes and `>` as its own, and an open script tag its nonce. Either would reach another host.
left_open() {
  local o
  o="$(open_panel "$1")"
  printf '%s' "$2" > "$(field "$o" draft)"
  publish "$1" >/dev/null
  step "left-open-${1:0:8}" "$(field "$o" address)" <<'JS'
async page => {
  const ctx = await page.context().browser().newContext();
  const foreign = [];
  await ctx.route('**/*', (route) => {
    const u = new URL(route.request().url());
    if (u.origin === '__ORIGIN__') return route.continue();
    foreign.push(u.href);
    return route.abort();
  });
  const p = await ctx.newPage();
  await p.goto('__PANEL__');
  await p.waitForTimeout(3000);
  const url = p.url();
  await ctx.close();
  const bad = [];
  if (url !== '__PANEL__') bad.push(`the page went to ${url}`);
  if (foreign.length) bad.push(`requests to another host: ${foreign.join(', ')}`);
  if (bad.length) throw new Error(bad.join('; '));
}
JS
}
left_open 0000dddd-1111-2222-3333-444444444444 \
  '<p>An open meta at the end.</p><meta http-equiv="refresh" content="0;url=https://invalid.example/'
left_open 0000eeee-1111-2222-3333-444444444444 \
  '<html><head><link rel="stylesheet" href="/base/panel.css"><script src="https://evil.example/x.js" a=</head><body><p>An open script tag.</p></body></html>'
left_open 0000ffff-1111-2222-3333-444444444444 \
  '<p>An open script tag at the end.</p><script src="https://evil.example/y.js" a="'
ok "a tag the draft leaves open takes neither the server script's quotes nor its nonce"

echo "all base checks passed"
