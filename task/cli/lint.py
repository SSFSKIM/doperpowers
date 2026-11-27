"""`task lint` (Interfaces §6) over a board's open issues: the FAILs, and the
WARNs that need no fold. It writes nothing."""
import shlex

import board as B


def _find(out, level, n, what, repair):
    out.append({"level": level, "number": n, "what": what, "repair": repair})


def _cycles(repo, nodes):
    """The strongly connected parts of the blocked-by graph among these
    open issues that hold a cycle, each as its numbers in order."""
    edges = {}
    for node in nodes:
        n = node["number"]
        edges[n] = [b["number"] for b in node["blockedBy"]["nodes"]
                    if b["repository"]["nameWithOwner"].lower() == repo.lower()]
    numbers = set(edges)
    index, low, on, stack, parts, counter = {}, {}, set(), [], [], [0]
    for root in sorted(numbers):
        if root in index:
            continue
        work = [(root, iter(edges[root]))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on.add(root)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in numbers:
                    continue
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(edges[w])))
                    advanced = True
                    break
                if w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                part = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    part.append(w)
                    if w == v:
                        break
                if len(part) > 1 or v in edges[v]:
                    parts.append(sorted(part))
    return parts


def lint(repo, nodes, login):
    """(findings, untracked count). A finding: level, number, what, repair."""
    out, untracked = [], 0
    for node in nodes:
        t = B.Ticket(repo, node, login)
        n, labels = t.number, t.labels
        readiness, horizons = B.readiness_of(labels), B.horizons_of(labels)
        statuses = B.statuses_of(labels)
        if statuses:
            _find(out, "FAIL", n, "a status label of the old vocabulary (%s)" % ", ".join(statuses),
                  "task set %d --readiness <R>, which takes it off" % n)
        if not readiness:
            untracked += 1
            if horizons:
                _find(out, "FAIL", n, "a horizon label (%s) on an open issue with no readiness label"
                      % ", ".join(horizons), "task set %d --readiness <R>" % n)
            if B.CLAIMED in labels:
                _find(out, "FAIL", n, "`claimed` on an open issue with no readiness label",
                      "task set %d --readiness <R>" % n)
            continue
        if len(readiness) > 1:
            _find(out, "FAIL", n, "more than one readiness label (%s)" % ", ".join(readiness),
                  "task set %d --readiness <R>" % n)
        if not horizons:
            _find(out, "FAIL", n, "no horizon label", "task set %d --horizon <H>" % n)
        elif len(horizons) > 1:
            _find(out, "FAIL", n, "more than one horizon label (%s)" % ", ".join(horizons),
                  "task set %d --horizon <H>" % n)
        priorities, categories = B.priorities_of(labels), B.categories_of(labels)
        if len(priorities) > 1:
            _find(out, "FAIL", n, "two priorities (%s)" % ", ".join(priorities), "task set %d --priority <P>" % n)
        elif not priorities:
            _find(out, "WARN", n, "no priority", "task set %d --priority <P>" % n)
        if len(categories) > 1:
            _find(out, "FAIL", n, "two categories (%s)" % ", ".join(categories), "task set %d --category <C>" % n)
        elif not categories:
            _find(out, "WARN", n, "no category", "task set %d --category <C>" % n)
        if t.body_trusted and t.parsed.problems:
            _find(out, "FAIL", n, "a malformed record block (%s)" % "; ".join(t.parsed.problems),
                  "task set %d --body-file <the prose>, which drops the unreadable block; then set its keys again "
                  "with --due, --spec and --to" % n)
        if horizons == ["planned"] and not t.blockers:
            _find(out, "WARN", n, "planned with no blocker: its order is decided and nothing says after what",
                  "task edge %d --block <N>, or task set %d --horizon expected" % (n, n))
        for b in t.blockers:
            if b["state"] in B.STUCK:
                same = b["repo"].lower() == repo.lower()
                shown = "#%d" % b["number"] if same else "%s#%d" % (b["repo"], b["number"])
                arg = "%d" % b["number"] if same else shlex.quote("%s#%d" % (b["repo"], b["number"]))
                how = "as not planned" if b["state"] == "not-planned" else "with no reason GitHub gives as completed"
                _find(out, "WARN", n, "a blocker closed %s (%s): stuck" % (how, shown),
                      "task edge %d --unblock %s, or task close %d --not-planned" % (n, arg, n))
    for part in _cycles(repo, nodes):
        a = part[0]
        nxt = next(b["number"] for node in nodes if node["number"] == a for b in node["blockedBy"]["nodes"]
                   if b["number"] in part)
        _find(out, "FAIL", a, "a blocked-by cycle (%s)" % ", ".join("#%d" % x for x in part),
              "task edge %d --unblock %d, or cut it elsewhere in the cycle" % (a, nxt))
    out.sort(key=lambda f: (f["level"] != "FAIL", f["number"]))
    return out, untracked
