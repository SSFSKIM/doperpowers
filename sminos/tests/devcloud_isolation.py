"""devcloud kept out of the sminos tests (T1's M5): imported first by every
runnable test file, so that a file run by itself is as hermetic as the
suite. What would ask devcloud (an end on purpose, the census) asks the
stand-in (devcloud_standin.py), and none of devcloud's own variables (its
seed key, its profile, which it reads ahead of HOME) reaches anything. The
one test of the real launcher (test_threads_owner.py) scrubs them again."""
import os

for _var in [v for v in os.environ if v.startswith("DEVCLOUD_")]:
    del os.environ[_var]
os.environ["SMINOS_DEVCLOUD"] = os.path.join(os.path.dirname(os.path.realpath(__file__)), "devcloud_standin.py")
