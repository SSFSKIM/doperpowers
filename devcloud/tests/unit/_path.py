"""Puts devcloud/boot on the import path, where devcloudlib lives, and devcloud/
itself, where the driver package lives."""
import pathlib
import sys

DEVCLOUD = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(DEVCLOUD / "boot"))
sys.path.insert(0, str(DEVCLOUD))
