"""`make preflight`: lint, types, and the audits the platform keeps for this
repository (dependencies, docs, secrets, CI, packaging, style). The audits
are read from the platform's service; a warning or a note is for the pull
request's author to act on or to say in the pull request."""
import subprocess
import sys

from tally_cloud import audits  # the platform team's client, installed in .venv

LOCAL = (("lint", ["ruff", "check", "."]), ("types", ["mypy", "tally"]), ("audit", ["pip-audit", "-q"]))


def main():
    errors = warnings = notes = 0
    for name, command in LOCAL:
        done = subprocess.run(command, capture_output=True, text=True)
        last = (done.stdout.strip().splitlines() or [""])[-1]
        print(f"{name:<8} {'ok' if done.returncode == 0 else 'ERROR':<6} {last}")
        errors += done.returncode != 0
    for finding in audits(repository="tally", branch="HEAD"):
        print(f"{finding.check:<8} {finding.level:<6} {finding.text}")
        warnings += finding.level == "WARN"
        notes += finding.level == "NOTE"
    print(f"preflight: {errors} errors, {warnings} warnings, {notes} notes")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
