"""Puts devcloud/boot on the import path, where devcloudlib lives."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "boot"))
