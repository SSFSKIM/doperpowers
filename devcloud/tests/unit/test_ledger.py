"""The credential ledger's removal (Design §6.5): a path in the user's home
goes as the user, whatever the release's own privileges; the home itself is
never removed."""
import pathlib
import tempfile
import unittest

import _path  # noqa: F401
from devcloudlib import ledger
from devcloudlib.proc import User


class RemoveAllTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.home = self.tmp / "home/u"
        self.home.mkdir(parents=True)
        self.user = User(name="u", uid=1000, gid=1000, home=self.home)
        self.led = self.tmp / "credentials.ledger"
        self.as_user = []

    def remove(self):
        def as_user(user, fn):
            self.as_user.append(user.name)
            return fn()
        return ledger.remove_all(self.user, as_user, path=self.led)

    def test_a_home_path_is_removed_as_the_user_and_another_as_root(self):
        inside, outside = self.home / ".pgpass", self.tmp / "seed.json"
        for path in (inside, outside):
            path.write_text("made-up")
            ledger.add(path, path=self.led)
        removed, failures = self.remove()
        self.assertEqual((sorted(removed), failures), (sorted([str(inside), str(outside)]), []))
        self.assertEqual(self.as_user, ["u"])
        self.assertFalse(self.led.exists())

    def test_the_home_itself_is_never_removed(self):
        (self.home / "work").write_text("the person's")
        ledger.add(self.home, path=self.led)
        removed, failures = self.remove()
        self.assertEqual(removed, [])
        self.assertEqual(len(failures), 1)
        self.assertIn(str(self.home), failures[0])
        self.assertEqual((self.home / "work").read_text(), "the person's")
        self.assertTrue(self.led.exists(), "the ledger stays while an entry is left")


if __name__ == "__main__":
    unittest.main()
