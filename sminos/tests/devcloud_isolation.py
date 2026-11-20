"""devcloud and the engine kept out of the sminos tests: imported first by
every runnable test file, so that a file run by itself is as hermetic as the
suite.

devcloud (T1's M5): what would ask devcloud (an end on purpose, the census)
asks the stand-in (devcloud_standin.py), and none of devcloud's own
variables (its seed key, its profile, which it reads ahead of HOME) reaches
anything. The one test of the real launcher (test_threads_owner.py) scrubs
them again.

The engine (T2's M3: a delivery may wake a stopped thread, and a wake lists
the engine's jobs and launches `claude`): `no-engine/claude` is first on
PATH, an empty job list and nothing started, so no test reaches the real
`claude` or what it reads; a suite that drives an engine of its own puts it
first ahead of this and checks it is the one found (test_wake.Engine)."""
import os

_HERE = os.path.dirname(os.path.realpath(__file__))
for _var in [v for v in os.environ if v.startswith("DEVCLOUD_")]:
    del os.environ[_var]
os.environ["SMINOS_DEVCLOUD"] = os.path.join(_HERE, "devcloud_standin.py")
_NO_ENGINE = os.path.join(_HERE, "no-engine")
if _NO_ENGINE not in os.environ.get("PATH", "").split(os.pathsep):   # once, never ahead of a test's own engine
    os.environ["PATH"] = _NO_ENGINE + os.pathsep + os.environ.get("PATH", "")
