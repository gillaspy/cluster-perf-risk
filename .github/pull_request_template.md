## What changes, and why

<!-- One or two sentences. Link an issue if there is one. -->

## Checks

- [ ] Unit tests pass inside the adapter image (same `TEST_COMMAND` the `verify` job runs)
- [ ] Docs updated for any user-visible change (README.md, MIGRATION.md, docs/METRICS.md)
- [ ] Touches a scoring threshold, weight, or formula: `tests/test_threshold_tables.py` updated, and MIGRATION.md/docs/METRICS.md note the change (bands change what color an object shows after upgrading)
- [ ] Touches the Suite API, credentials, TLS, or logging: checked that nothing sensitive (tokens, passwords) can reach `adapter.log`
- [ ] `manifest.txt` left unchanged -- the release tag sets the version (see "Build and release" in README.md)
- [ ] If an AI assistant wrote most of this change: said so above, and what was checked by hand
