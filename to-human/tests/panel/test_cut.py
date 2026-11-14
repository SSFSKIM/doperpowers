#!/usr/bin/env python3
"""What publishing cuts from a draft (server.py's `cut`): every <meta http-equiv>, every <link> but a stylesheet
under /base/, every <base>, found as a browser's tokenizer finds a start tag, wherever it stands in the source; the
rest of the source byte for byte.

Run: python3 -m unittest discover -s to-human/tests/panel
"""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True      # loading server.py must leave no __pycache__ in the plugin
SERVER_PY = Path(__file__).resolve().parents[2] / "panel" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("panel_server", SERVER_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = load_server()

HEAD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>T</title>\n'
        '<link rel="stylesheet" href="/base/panel.css">\n<script src="/base/panel.js" defer></script>\n')


class Cut(unittest.TestCase):
    def test_a_clean_page_is_left_byte_for_byte(self):
        page = HEAD + "</head>\n<body>\n<h1>Plan</h1>\n<p>Text with <mark data-note=\"u1-1\">a note</mark>.</p>\n</body>\n</html>\n"
        self.assertEqual(S.cut(page), (page, []))

    def test_refresh_prefetch_and_base_are_cut_and_the_rest_kept(self):
        refresh = '<meta http-equiv="refresh" content="0;url=https://example.com/">'
        prefetch = '<link rel="dns-prefetch" href="//evil.example">'
        base = '<base href="https://evil.example/">'
        page = HEAD + refresh + "\n" + prefetch + "\n" + base + "\n</head>\n<body><p>x</p></body>\n"
        out, removed = S.cut(page)
        self.assertEqual(out, HEAD + "\n\n\n</head>\n<body><p>x</p></body>\n")
        self.assertEqual(removed, ["meta http-equiv", "link", "base"])

    def test_any_case_and_unquoted_forms(self):
        out, removed = S.cut("<p>a</p><META HTTP-EQUIV=Refresh CONTENT=0;url=https://x/><p>b</p>")
        self.assertEqual(out, "<p>a</p><p>b</p>")
        self.assertEqual(removed, ["meta http-equiv"])
        out, _ = S.cut("<LiNk ReL=preconnect HREF=https://x/ />z")
        self.assertEqual(out, "z")

    def test_a_quoted_gt_does_not_end_the_tag(self):
        out, _ = S.cut('<meta content="a>b" http-equiv="refresh">after')
        self.assertEqual(out, "after")

    def test_links_kept_are_base_stylesheets_alone(self):
        keep = ['<link rel="stylesheet" href="/base/panel.css">', "<link href=/base/extra.css rel=STYLESHEET>"]
        for tag in keep:
            self.assertEqual(S.cut(tag), (tag, []), tag)
        cut = ['<link rel="stylesheet" href="https://evil.example/x.css">', '<link rel="stylesheet" href="//evil/base/x.css">',
               '<link rel="stylesheet preload" href="/base/panel.css">', '<link rel="icon" href="/base/panel.css">',
               '<link rel="stylesheet" href="base/panel.css">', '<link rel="prefetch" href="/x">', "<link>"]
        for tag in cut:
            self.assertEqual(S.cut(tag), ("", ["link"]), tag)

    def test_a_meta_without_http_equiv_stays(self):
        tag = '<meta name="referrer" content="no-referrer">'
        self.assertEqual(S.cut(tag), (tag, []))

    def test_what_html_parser_misreads_is_cut_too(self):
        # html.parser reads `<!-->` as the start of a comment running to the next `-->`; a browser closes the
        # comment at once, so the meta is live there.
        page = '<!--><meta http-equiv=refresh content="0;url=https://x/"><!-- -->'
        out, removed = S.cut(page)
        self.assertNotIn("meta", out.lower())
        self.assertEqual(removed, ["meta http-equiv"])

    def test_a_cut_cannot_join_the_pieces_of_a_new_tag(self):
        out, removed = S.cut("<me<meta http-equiv=x>ta http-equiv=refresh content=0;url=https://x/>tail")
        self.assertNotIn("<meta", out.lower())
        self.assertEqual(removed, ["meta http-equiv"])
        self.assertTrue(out.endswith("tail"))

    def test_a_tag_left_open_is_cut_to_the_end(self):
        self.assertEqual(S.cut('<p>a</p><base href="https://x/'), ("<p>a</p>", ["base"]))

    def test_names_that_only_begin_alike_are_other_tags(self):
        page = "<metadata>x</metadata><linked>y</linked><basefont>"
        self.assertEqual(S.cut(page), (page, []))


if __name__ == "__main__":
    unittest.main()
