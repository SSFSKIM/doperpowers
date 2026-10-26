#!/usr/bin/env python3
"""A desk upload's files on the machine (the desk control surface's MW5):
written under the session's working directory without following a link,
idempotent by upload, excluded from git, and swept once the session has run
nowhere here for a day.

Hermetic: HOME and SMINOS_HOME are temporary (test_session_plane's)."""

import base64
import json
import os
import subprocess
import time
import unittest
import uuid as uuidlib

import test_session_plane as tsp  # noqa: E402 — first: it makes this run's HOME and SMINOS_HOME

import sminos  # noqa: E402
import sminos_daemon as daemon  # noqa: E402
import sminos_media as media  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"
NONCE = "AAAAAAAAAAAAAAAAAAAAAA"


def b64(data):
    return base64.b64encode(data).decode("ascii")


def attachment(name, media_type, data):
    return {"name": name, "mediaType": media_type, "data": b64(data)}


class Shape(unittest.TestCase):
    def test_each_type_is_its_bytes_signature(self):
        self.assertEqual(media.type_of(PNG), "image/png")
        self.assertEqual(media.type_of(b"\xff\xd8\xff\xe0rest"), "image/jpeg")
        self.assertEqual(media.type_of(b"GIF89a..."), "image/gif")
        self.assertEqual(media.type_of(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "image/webp")
        self.assertEqual(media.type_of(PDF), "application/pdf")
        self.assertIsNone(media.type_of(b"RIFF\x00\x00\x00\x00WAVE"))
        self.assertIsNone(media.type_of(b"plain text"))

    def test_the_attachments_shape(self):
        good = attachment("shot.png", "image/png", PNG)
        self.assertIsNone(media.why_not([good]))
        self.assertIsNone(media.why_not([good] * 4), "four, the same name twice too: names are for display")
        for bad in ([], [good] * 5, "x", [5], [{**good, "name": ""}], [{**good, "name": ".hidden"}],
                    [{**good, "name": "a/b.png"}], [{**good, "name": "x" * 129}],
                    [{**good, "mediaType": "image/tiff"}], [{**good, "mediaType": "application/pdf"}],
                    [{**good, "data": "not base64!"}], [{**good, "data": b64(PNG)[:-2]}], [{**good, "data": ""}],
                    [{**good, "data": b64(PNG) + "\n"}]):
            self.assertIsNotNone(media.why_not(bad), bad)


class Save(unittest.TestCase):
    def setUp(self):
        self.base = os.path.realpath(os.path.join(tsp.T, "cwd-" + uuidlib.uuid4().hex[:8]))
        os.makedirs(self.base)
        self.sid = str(uuidlib.uuid4())

    def test_files_are_named_by_the_upload_and_their_type_not_the_name_given(self):
        root, names = media.save(self.base, self.sid, NONCE, [attachment("photo", "image/png", PNG),
                                                             attachment("photo", "application/pdf", PDF),
                                                             attachment("photo.jpg", "image/png", PNG)])
        self.assertEqual(root, os.path.join(self.base, ".claude", "desk-uploads", self.sid))
        self.assertEqual(names, [NONCE + ".0.png", NONCE + ".1.pdf", NONCE + ".2.png"],
                         "a missing or mismatched suffix, and the same name twice, are the display's alone")
        for name, data in zip(names, (PNG, PDF, PNG)):
            with open(os.path.join(root, name), "rb") as f:
                self.assertEqual(f.read(), data)
            self.assertEqual(os.stat(os.path.join(root, name)).st_mode & 0o777, 0o600)
        for d in (os.path.join(self.base, ".claude"), os.path.dirname(root), root):
            self.assertEqual(os.stat(d).st_mode & 0o777, 0o700, d)
        self.assertEqual(media.roots(self.sid), [root], "recorded for the sweep")

    def test_saving_again_is_idempotent_and_other_bytes_are_refused(self):
        files = [attachment("a.png", "image/png", PNG)]
        first = media.save(self.base, self.sid, NONCE, files)
        self.assertEqual(media.save(self.base, self.sid, NONCE, files), first, "the same bytes: saved")
        with self.assertRaises(media.Unsafe):
            media.save(self.base, self.sid, NONCE, [attachment("a.png", "image/png", PNG + b"more")])
        self.assertEqual(media.roots(self.sid), [first[0]], "recorded once")

    def test_a_symlinked_directory_component_refuses_the_upload(self):
        elsewhere = os.path.join(tsp.T, "elsewhere-" + uuidlib.uuid4().hex[:8])
        os.makedirs(elsewhere)
        for component in (".claude", ".claude/desk-uploads", ".claude/desk-uploads/" + self.sid):
            base = os.path.realpath(os.path.join(tsp.T, "cwd-" + uuidlib.uuid4().hex[:8]))
            parent = os.path.dirname(os.path.join(base, component))
            os.makedirs(parent, exist_ok=True)
            os.symlink(elsewhere, os.path.join(base, component))
            with self.assertRaises(media.Unsafe, msg=component):
                media.save(base, self.sid, NONCE, [attachment("a.png", "image/png", PNG)])
        self.assertEqual(os.listdir(elsewhere), [], "nothing written through a link")

    def test_a_component_that_is_a_file_refuses_the_upload(self):
        with open(os.path.join(self.base, ".claude"), "w") as f:
            f.write("not a directory")
        with self.assertRaises(media.Unsafe):
            media.save(self.base, self.sid, NONCE, [attachment("a.png", "image/png", PNG)])

    def test_a_symlinked_leaf_refuses_the_upload(self):
        target = os.path.join(tsp.T, "target-" + uuidlib.uuid4().hex[:8])
        with open(target, "wb") as f:
            f.write(b"theirs")
        root = os.path.join(self.base, ".claude", "desk-uploads", self.sid)
        os.makedirs(root)
        os.symlink(target, os.path.join(root, NONCE + ".0.png"))
        with self.assertRaises(media.Unsafe):
            media.save(self.base, self.sid, NONCE, [attachment("a.png", "image/png", PNG)])
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"theirs", "never written through")

    def test_remove_takes_the_named_files_and_an_emptied_root(self):
        root, names = media.save(self.base, self.sid, NONCE, [attachment("a.png", "image/png", PNG)])
        other = media.save(self.base, self.sid, "BBBBBBBBBBBBBBBBBBBBBB", [attachment("b.pdf", "application/pdf", PDF)])[1]
        media.remove(root, names)
        self.assertEqual(os.listdir(root), other, "another upload's files stay")
        media.remove(root, other)
        self.assertFalse(os.path.exists(root), "an emptied root goes")


class Exclude(unittest.TestCase):
    def test_the_line_is_added_once_to_the_repositorys_common_exclude(self):
        repo = os.path.realpath(os.path.join(tsp.T, "repo-" + uuidlib.uuid4().hex[:8]))
        sub = os.path.join(repo, "pkg")
        os.makedirs(sub)
        subprocess.run(["git", "init", "-q", repo], check=True)
        exclude = os.path.join(repo, ".git", "info", "exclude")
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "w") as f:
            f.write("*.log")   # no final newline
        self.assertTrue(media.exclude(sub))
        self.assertTrue(media.exclude(repo))
        with open(exclude) as f:
            self.assertEqual(f.read(), "*.log\n**/.claude/desk-uploads/\n")
        sid = str(uuidlib.uuid4())
        media.save(sub, sid, NONCE, [attachment("a.png", "image/png", PNG)])
        status = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=all"],
                                capture_output=True, text=True, check=True).stdout
        self.assertNotIn("desk-uploads", status, "an upload in a subdirectory's session never shows")

    def test_outside_a_repository_nothing_is_excluded(self):
        bare = os.path.realpath(os.path.join(tsp.T, "plain-" + uuidlib.uuid4().hex[:8]))
        os.makedirs(bare)
        self.assertFalse(media.exclude(bare))


class Sweep(unittest.TestCase):
    def test_the_daemon_sweeps_an_ended_sessions_uploads_once_it_has_been_quiet_a_day(self):
        old = time.time() - 2 * 86400
        transcripts = os.path.join(os.environ["HOME"], ".claude", "projects", "-uploads")
        os.makedirs(transcripts, exist_ok=True)
        roots = {}
        for k in ("quiet", "recent"):
            sid = str(uuidlib.uuid4())
            base = os.path.realpath(os.path.join(tsp.T, "cwd-" + uuidlib.uuid4().hex[:8]))
            os.makedirs(base)
            roots[k] = (sid, media.save(base, sid, NONCE, [attachment("a.png", "image/png", PNG)])[0])
            t = os.path.join(transcripts, sid + ".jsonl")
            with open(t, "w") as f:
                f.write("{}\n")
            if k == "quiet":
                os.utime(t, (old, old))
                os.utime(media.record_path(sid), (old, old))
        # A link planted where the quiet session's root was: the sweep removes nothing through it.
        planted = os.path.join(tsp.T, "planted-" + uuidlib.uuid4().hex[:8])
        os.makedirs(planted)
        with open(os.path.join(planted, "keep.txt"), "w") as f:
            f.write("theirs")
        q_sid, q_root = roots["quiet"]
        moved = q_root + ".moved"
        os.rename(q_root, moved)
        os.symlink(planted, q_root)
        sminos.forget_caches()
        daemon.sweep_uploads()
        self.assertEqual(os.listdir(planted), ["keep.txt"], "nothing removed through a link")
        self.assertFalse(os.path.exists(media.record_path(q_sid)), "its record goes")
        self.assertTrue(os.path.exists(os.path.join(roots["recent"][1], NONCE + ".0.png")), "a recent session's stay")
        os.unlink(q_root)
        os.rename(moved, q_root)
        media.record(q_sid, q_root)
        os.utime(media.record_path(q_sid), (old, old))
        daemon.sweep_uploads()
        self.assertFalse(os.path.exists(q_root), "the quiet session's uploads are swept")
        self.assertNotIn(q_sid, media.recorded())
        self.assertIn(roots["recent"][0], media.recorded())


if __name__ == "__main__":
    unittest.main()
