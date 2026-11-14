// The panel's base script. It draws each open note beside its anchor in the margin (under the anchor's block on a
// narrow window) with a check button, counts the open notes at the top with a jump to the next, reports a check
// and a look to the server, and reloads the page, keeping its scroll, when the server has published it anew.
// The server inserts window.PANEL = {written, checked} before </head>; this file is linked `defer`, so it runs
// once the document is parsed. Its words are English or Korean, by the page's lang.
(() => {
  'use strict';

  const WORDS = {
    en: {
      count: (n) => (n === 1 ? '1 note on what changed' : `${n} notes on what changed`),
      next: 'Next note',
      check: 'Mark as read',
      unsaved: 'Not saved: try again',
    },
    ko: {
      count: (n) => `바뀐 내용 메모 ${n}개`,
      next: '다음 메모',
      check: '읽음으로 표시',
      unsaved: '저장되지 않았습니다. 다시 눌러 주세요',
    },
  };
  const WIDE = '(min-width: 68rem)';
  const POLL_MS = 2000;
  const NOTE_ID = /^u\d+-\d+$/;

  // The server's script is missing when a page's head comment names </head>: the script lands inside the
  // comment. Then the first answer of /written stands for the page shown (known: whether its time is known),
  // and checked notes draw until the next publication.
  const panel = window.PANEL || { written: null, checked: [] };
  let known = Boolean(window.PANEL);
  const short = location.pathname.split('/')[1] || '';
  const lang = (document.documentElement.lang || 'en').toLowerCase().split('-')[0];
  const words = WORDS[lang] || WORDS.en;
  const scrollKey = `panel-scroll:${short}`;
  const html = document.documentElement;
  const body = document.body;

  const checked = new Set(panel.checked || []);
  const notes = [...document.querySelectorAll('aside.note[id]')].filter((n) => NOTE_ID.test(n.id));
  const anchorsOf = (id) => [...document.querySelectorAll(`mark[data-note="${CSS.escape(id)}"]`)];
  const isOpen = (n) => !checked.has(n.id);
  let mode = null;            // 'wide' | 'narrow' once laid out
  let margin = null;          // the margin layer, made on the first wide layout

  // ---- the notes

  for (const n of notes) {
    const label = n.getAttribute('data-label');
    if (label) {
      const what = document.createElement('p');
      what.className = 'what';
      what.textContent = label;
      n.prepend(what);
    }
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'check';
    b.textContent = '✓';
    b.title = words.check;
    b.setAttribute('aria-label', `${words.check}: ${n.textContent.trim().slice(0, 60)}`);
    b.addEventListener('click', () => check(n));
    n.prepend(b);
    const hot = (on) => anchorsOf(n.id).forEach((m) => m.classList.toggle('is-hot', on));
    n.addEventListener('mouseenter', () => hot(true));
    n.addEventListener('mouseleave', () => hot(false));
    n.addEventListener('focusin', () => hot(true));
    n.addEventListener('focusout', () => hot(false));
    for (const m of anchorsOf(n.id)) {
      m.addEventListener('mouseenter', () => n.classList.add('is-hot'));
      m.addEventListener('mouseleave', () => n.classList.remove('is-hot'));
    }
  }

  // Where a note's anchor shows: its first mark, or the summary of the closed details that hides it.
  const shownAnchor = (n) => {
    const m = anchorsOf(n.id)[0];
    if (!m) return null;
    let closed = m.closest('details:not([open])');
    while (closed && closed.parentElement && closed.parentElement.closest('details:not([open])')) {
      closed = closed.parentElement.closest('details:not([open])');
    }
    return closed ? closed.querySelector(':scope > summary') || closed : m;
  };
  const anchorTop = (n) => {
    const a = shownAnchor(n);
    return a ? a.getBoundingClientRect().top + window.scrollY : Infinity;
  };
  const openNotes = () => notes.filter(isOpen).sort((a, b) => anchorTop(a) - anchorTop(b));

  // Under the anchor's block: inside a list item or a cell, else after the paragraph, heading or block.
  const inlineSpot = (n) => {
    const m = anchorsOf(n.id)[0];
    if (!m) return null;
    const cell = m.closest('li, td, th, dd, dt');
    if (cell) return { inside: cell };
    let block = m.closest('p, h1, h2, h3, h4, h5, h6, pre, blockquote, figure, table, ul, ol, dl, summary');
    if (block && block.tagName === 'SUMMARY') block = block.parentElement;
    return { after: block || m };
  };

  const placeInline = () => {
    const last = new Map();
    for (const n of openNotes()) {
      const spot = inlineSpot(n);
      if (!spot) continue;
      n.style.top = '';
      if (spot.inside) {
        spot.inside.append(n);
      } else {
        (last.get(spot.after) || spot.after).after(n);
        last.set(spot.after, n);
      }
    }
  };

  const placeInMargin = () => {
    if (!margin) {
      margin = document.createElement('div');
      margin.className = 'panel-margin';
      margin.setAttribute('role', 'complementary');
    }
    if (margin.parentNode !== body) body.append(margin);
    for (const n of openNotes()) if (anchorsOf(n.id).length && n.parentNode !== margin) margin.append(n);
  };

  const stack = () => {
    if (mode !== 'wide') return;
    const top0 = body.getBoundingClientRect().top + window.scrollY;
    let floor = 0;
    for (const n of openNotes()) {
      if (n.parentNode !== margin) continue;
      const want = Math.max(anchorTop(n) - top0 - 4, floor);
      n.style.top = `${Math.round(want)}px`;
      floor = want + n.offsetHeight + 8;
    }
  };

  const layout = () => {
    const open = openNotes();
    for (const n of notes) {
      n.classList.toggle('is-open', isOpen(n));
      anchorsOf(n.id).forEach((m) => m.classList.toggle('is-open', isOpen(n)));
    }
    const want = open.some((n) => anchorsOf(n.id).length) && window.matchMedia(WIDE).matches ? 'wide' : 'narrow';
    html.classList.toggle('panel-wide', want === 'wide');
    if (want !== mode) {
      mode = want;
      if (want === 'wide') placeInMargin();
      else placeInline();
    }
    stack();
    drawBar(open.length);
  };

  let queued = false;
  const relayout = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      layout();
    });
  };

  // ---- the count, and the jump to the next note

  let bar = null;
  const drawBar = (count) => {
    if (count === 0) {
      if (bar) bar.hidden = true;
      return;
    }
    if (!bar) {
      bar = document.createElement('div');
      bar.className = 'panel-notebar';
      bar.setAttribute('role', 'status');
      const said = document.createElement('span');
      const next = document.createElement('button');
      next.type = 'button';
      next.textContent = words.next;
      next.addEventListener('click', jump);
      bar.append(said, next);
      body.prepend(bar);
    }
    bar.hidden = false;
    bar.firstChild.textContent = words.count(count);
  };

  // The next note: the one after the note last jumped to while that one is still in view, else the first whose
  // anchor is below the top of the window.
  let lastJump = null;
  const inView = (n) => {
    const a = shownAnchor(n) || n;
    const r = a.getBoundingClientRect();
    return r.bottom > 0 && r.top < window.innerHeight;
  };
  const jump = () => {
    const open = openNotes();
    if (!open.length) return;
    let i = lastJump ? open.indexOf(lastJump) : -1;
    if (i >= 0 && inView(lastJump)) {
      i = (i + 1) % open.length;
    } else {
      const line = window.scrollY + (bar ? bar.offsetHeight : 0) + 24;
      i = Math.max(0, open.findIndex((o) => anchorTop(o) > line));
    }
    const n = open[i];
    lastJump = n;
    const m = anchorsOf(n.id)[0];
    if (m) {
      for (let d = m.closest('details:not([open])'); d; d = m.closest('details:not([open])')) d.open = true;
      layout();
    }
    (m || n).scrollIntoView({ block: 'center' });
    const hot = [n, ...anchorsOf(n.id)];
    hot.forEach((e) => e.classList.add('is-hot'));
    setTimeout(() => hot.forEach((e) => e.classList.remove('is-hot')), 1200);
    n.querySelector('.check')?.focus({ preventScroll: true });
  };

  // ---- a check, kept by the server

  const post = (what, value) =>
    fetch(`/${short}/${what}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(value),
      cache: 'no-store',
    }).then((r) => {
      if (!r.ok) throw new Error(String(r.status));
    });

  const check = (n) => {
    checked.add(n.id);
    const after = openNotes();
    layout();
    const next = after.find((o) => n.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING) || after[0];
    next?.querySelector('.check')?.focus({ preventScroll: true });
    post('check', { note: n.id }).catch(() => {
      checked.delete(n.id);
      layout();
      const b = n.querySelector('.check');
      if (b) b.title = words.unsaved;
    });
  };

  // ---- a look: the publication drawn in a visible tab

  let told = false;
  const look = () => {
    if (told || !known || panel.written == null || document.visibilityState !== 'visible') return;
    told = true;
    post('seen', { written: panel.written }).catch(() => {
      told = false;
    });
  };

  // ---- a new publication: reload once, where the reader was

  let timer = null;
  let reloading = false;
  const poll = () => {
    clearTimeout(timer);
    timer = null;
    if (reloading || document.visibilityState !== 'visible') return;
    fetch(`/${short}/written`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (j && !known) {
          known = true;
          panel.written = j.written;
          look();
        } else if (j && j.written != null && j.written !== panel.written) {
          reloading = true;
          location.reload();
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!reloading && document.visibilityState === 'visible' && timer === null) timer = setTimeout(poll, POLL_MS);
      });
  };

  history.scrollRestoration = 'manual';
  window.addEventListener('pagehide', () => {
    try {
      sessionStorage.setItem(scrollKey, String(Math.round(window.scrollY)));
    } catch {}
  });
  const restoreScroll = () => {
    let y = null;
    try {
      y = sessionStorage.getItem(scrollKey);
      sessionStorage.removeItem(scrollKey);
    } catch {}
    if (y !== null && Number.isFinite(+y)) window.scrollTo(0, +y);
  };

  // ---- start

  layout();
  restoreScroll();
  look();
  window.addEventListener('resize', relayout);
  document.addEventListener('toggle', relayout, true);
  window.addEventListener('load', relayout);
  if (document.fonts) document.fonts.ready.then(relayout);
  if (window.ResizeObserver) new ResizeObserver(relayout).observe(body);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      look();
      poll();
    }
  });
  timer = setTimeout(poll, known ? POLL_MS : 0);
})();
