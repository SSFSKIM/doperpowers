.PHONY: test lint fixtures smoke-staging

test:
	pytest -q

lint:
	ruff check . && mypy tally

# The 2M-row usage fixture the slow tests read (about a minute).
fixtures:
	python -m tests.fixtures.generate --rows 2000000 --out .fixtures/usage_2m.sql

# Every report type for the five largest accounts of last night's staging
# snapshot, through tally.export, files to /tmp/smoke/. Read-only on staging.
smoke-staging:
	python -m tests.smoke.staging --top 5 --out /tmp/smoke
