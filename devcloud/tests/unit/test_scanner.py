import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest

SCANNER = pathlib.Path(__file__).resolve().parents[1] / "scan-secrets.ts"
PLANTED = "made-up-planted-value-93Xk"
CHUNK = 16 << 20


@unittest.skipUnless(shutil.which("bun"), "bun runs the scanner")
class KnownValueScanTest(unittest.TestCase):
    """Acceptance 6(a) covers every byte of the image: binaries and files past
    the pattern detector's size limit are scanned for known values too."""

    def scan(self, root):
        result = subprocess.run(["bun", str(SCANNER), "scan", str(root), "--values", "-"],
                                input=json.dumps([PLANTED]), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return {line.split("\t")[1][len(str(root)):] for line in result.stdout.splitlines()
                if line.startswith("known\t")}

    def test_finds_a_value_in_a_file_with_a_nul_byte(self):
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "binary").write_bytes(b"\x7fELF\x00\x01\x02 header " + PLANTED.encode() + b"\x00 tail")
        self.assertEqual(self.scan(root), {"/binary"})

    def test_finds_values_in_a_file_past_the_size_limit_across_a_chunk_boundary(self):
        root = pathlib.Path(tempfile.mkdtemp())
        value = PLANTED.encode()
        with open(root / "straddle", "wb") as f:   # the value spans the first chunk boundary
            f.write(b"\0" * (CHUNK - 10) + value + b"\0" * (70 << 20))
        with open(root / "tail", "wb") as f:       # the value is the file's last bytes
            f.write(b"\0" * (70 << 20) + value)
        self.assertEqual(self.scan(root), {"/straddle", "/tail"})

    def test_finds_an_encoded_spelling_in_a_binary(self):
        import base64
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "blob").write_bytes(b"\x00\x00" + base64.b64encode(PLANTED.encode()) + b"\x00")
        self.assertEqual(self.scan(root), {"/blob"})


if __name__ == "__main__":
    unittest.main()
