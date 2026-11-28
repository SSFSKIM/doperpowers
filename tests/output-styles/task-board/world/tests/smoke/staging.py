"""The staging smoke (`make smoke-staging`): every report type for the largest
accounts of last night's staging snapshot, written through tally.export.
Read-only on staging. Needs a session of the profile tally-staging
(`tally-cloud login --profile tally-staging`)."""
import argparse
import sys
import time
from pathlib import Path

from tally_cloud import NoSession, session  # the platform team's client, installed in .venv

from tally.export import ExportTooLarge, export_columns, write_csv
from tally.reports.models import ReportType
from tally.reports.query import iter_rows

PROFILE = "tally-staging"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("/tmp/smoke"))
    args = ap.parse_args(argv)
    try:
        staging = session(PROFILE)
    except NoSession as e:
        print(f"staging: no valid session for the profile {PROFILE} ({e})\n"
              f"  sign in with: tally-cloud login --profile {PROFILE}")
        return 3
    print(f"staging snapshot {staging.snapshot}; {args.top} accounts x {len(ReportType)} report types; "
          f"{staging.period:%B %Y}")
    args.out.mkdir(parents=True, exist_ok=True)
    refused = 0
    for account in staging.largest_accounts(args.top):
        for kind in ReportType:
            report = staging.report(account, kind)
            started = time.monotonic()
            try:
                with open(args.out / f"{account.slug}-{kind.value}.csv", "w", newline="") as out:
                    n = write_csv(iter_rows(report), export_columns(staging.role, report), out,
                                  timezone=account.timezone, total=report.row_count)
            except ExportTooLarge as e:
                refused += 1
                print(f"{account.slug:<17} {kind.value:<15} {report.row_count:>9,} rows   --     ExportTooLarge: {e}")
                continue
            print(f"{account.slug:<17} {kind.value:<15} {n:>9,} rows  {time.monotonic() - started:4.1f}s  "
                  f"peak RSS {staging.peak_rss_mb():.0f} MB  ok")
    for note in staging.notes():
        print("note:", note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
