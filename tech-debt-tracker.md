# Technical debt

| Area | Finding | Disposition |
| --- | --- | --- |
| Guard provenance status | `devcloud/hooks/mods/secrets-provenance.py`, `metadata()` assumes decoded metadata is an object. A malformed row containing a JSON array makes `guard status --json` raise instead of reporting `unknown/invalid_index`. | Deferred from board ticket 124's M1 review: diagnostic robustness only; runtime verification still falls back. Validate the decoded type and add a focused status regression. |
| Guard provenance cache test | `devcloud/tests/mods/provenance_index_test.py`, `test_private_metadata_only_cache_and_read_only_verify` searches for a sentinel absent from its source fixture, so that assertion cannot detect persisted source bytes. | Deferred from board ticket 124's M1 review: the implementation stores metadata/digests, but this assertion needs an actual fixture sentinel. Put the sentinel in the source and assert its absence from every cache file. |
