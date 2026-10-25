"""The check behind the evals' deny-readers plugin, which both configurations
load: a fetch through a third-party reader, renderer or proxy is refused, for
the reason Bash is left out of both: each configuration reads the web through
its own fetch tool. The hard set's screening found the runner reaching pages
WebFetch could not read through these services (r.jina.ai, wsrv.nl
rasterizing a PDF's pages, Google's document viewer).

Reads `{"tool_name", "tool_input": {"url"}}` on stdin (a hook event's shape);
exits 2 with the reason on stderr, which the plugin's mod returns as the
call's deny, else 0.
"""

import json
import sys
import urllib.parse

FETCH_TOOLS = ('WebFetch', 'mcp__web__fetch')
# Hosts refused whole, with their subdomains.
READER_HOSTS = (
    'r.jina.ai', 's.jina.ai',                         # Jina's reader and search-reader
    'wsrv.nl', 'images.weserv.nl',                    # an image proxy that also rasterizes PDF pages
    'translate.goog', 'translate.google.com',         # Google Translate's page proxy
    'archive.org',                                    # the Wayback Machine (web.archive.org)
    'archive.ph', 'archive.today', 'archive.is',      # archive.today's mirrors
)
# Google's document viewer renders any URL it is given; the rest of docs.google.com is Google Docs.
READER_PATHS = {'docs.google.com': ('/viewer', '/gview', '/viewerng')}


def refused(url):
    """The reader `url` goes through, or None."""
    parts = urllib.parse.urlsplit(url or '')
    host = (parts.hostname or '').rstrip('.')
    for h in READER_HOSTS:
        if host == h or host.endswith('.' + h):
            return h
    for h, prefixes in READER_PATHS.items():
        for prefix in prefixes if host == h else ():
            if parts.path == prefix or parts.path.startswith(prefix + '/'):
                return h + prefix
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    if event.get('tool_name') not in FETCH_TOOLS:
        return 0
    reader = refused((event.get('tool_input') or {}).get('url'))
    if not reader:
        return 0
    print(f'Refused: {reader} is a third-party reader or proxy, and the web is read here only through your own '
          f'fetch tool. Fetch the page itself, or another source of the same document.', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
