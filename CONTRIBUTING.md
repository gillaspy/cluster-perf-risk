# Contributing

Thank you for wanting to help. Every kind of contribution below is useful.

## Ways to help, without writing code

| What you can do | How |
| :--- | :--- |
| **Run it and report what you see** | Install the pack on a test instance, then open an issue. Include the version, the Adapter Instance settings (credentials removed -- there aren't any to remove, this adapter is self-referential), and the relevant lines from `adapter.log`. |
| **Improve the documentation** | Fix a sentence, add an example, or explain a symptom you hit, in README.md, MIGRATION.md or docs/METRICS.md. |
| **Share dashboards or super metrics** | Export them from VCF Operations and open a pull request, with a note on what they show. |

## Reporting a problem

See [SECURITY.md](SECURITY.md) for a vulnerability. For anything else, open an issue with:

- The pack version and the VCF Operations version.
- What you expected, and what you saw.
- The lines of `adapter.log` around the time of the problem.
- Whether it happens every cycle, or now and then.

Remove passwords, tokens and the names of private hosts before you post.

## Add code, with or without an AI coding assistant

You are welcome to use an AI coding assistant to write a change, and the same standard applies whoever or whatever wrote it.

**What we expect from any change:**

- **You understand it.** You can explain every line in the pull request, and you have read the code around it.
- **It is small and focused.** One topic per pull request. A rename across the whole project should be discussed first.
- **It has tests.** `tests/` has worked examples for every formula; add one in the same style for anything new. Tests run inside the adapter image, the way CI runs them (see `TEST_COMMAND` in `.github/workflows/build-and-publish.yml`), not against a live VCF Operations instance.
- **It has documentation.** A new or changed metric needs a row in [docs/METRICS.md](docs/METRICS.md); anything user-visible needs a line in [README.md](README.md) or [MIGRATION.md](MIGRATION.md).
- **It has no secrets.** No passwords, tokens, real hostnames or `connections.json`-style files, in code, tests, docs or screenshots.
- **It says how it was made.** If an assistant wrote most of it, say so in the pull request, and say what you checked by hand or against a real instance. This helps the reviewer; it does not count against you.

**A threshold or weight change is not routine.** It changes what color an object shows after upgrading, on every instance running the pack. State the old and new values, why, and what you confirmed it against (live data if at all possible -- see the `# confirmed live` style of comment already in `thresholds_*.py`), and update `tests/test_threshold_tables.py`, `docs/METRICS.md` and `MIGRATION.md`.

## The workflow

1. Fork the repository, and create a branch for your change off `main`.
2. Make the change, with its tests and documentation.
3. Run the tests inside the adapter image (see "Build and release" in README.md for the build steps `verify` runs).
4. Open a pull request against `main`. Say what changed, why, how you tested it, and whether an assistant was used.
5. Respond to review. A reviewer may ask for a change, a test, or a simpler approach -- that's normal.

Small fixes (typos, a clearer sentence) don't need an issue first; open a pull request straight away.

## Support

This is a personal project with no formal support. See [SECURITY.md](SECURITY.md) for vulnerabilities specifically; everything else goes through an issue or pull request on this repository.

Thank you for helping.
