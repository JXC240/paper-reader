# Development and automated checks

Paper Reader uses a small Python HTTP server, PDF.js browser assets, and plain JavaScript. The reader itself does not require Node.js. Node and Playwright are only needed for development checks.

## Prepare a checkout

Use Python 3.10 or later. From the repository root:

```sh
./start.sh --prepare-only
```

This creates the local `.venv`, installs exact dependencies from `requirements.txt`, downloads the pinned PDF.js archive, verifies its SHA-512 integrity, and checks essential browser assets. A matching version marker with missing or empty essential files triggers repair. Initial preparation needs network access; it does not open a browser or change a macOS login item.

If Python is missing or too old, the launcher stops with instructions. A failed virtual-environment creation commonly means `venv`/`ensurepip` is unavailable; some Linux distributions package it as `python3-venv`. If a moved checkout has a broken `.venv`, rename that environment and prepare again with a supported Python. Preserve `data/`.

## Run the checks

Python unit, storage, HTTP, startup, and background-management checks:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

The background-management tests use mocks and temporary directories. They do not install, unload, or modify your real macOS LaunchAgent. Storage/HTTP tests use temporary libraries.

Search checks need Node.js, with no npm packages required:

```sh
node --test tests/search.mjs
```

For browser checks, use Node 22 and pnpm 10 (the CI configuration):

```sh
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
PAPER_READER_BROWSER_CHANNEL=bundled pnpm test:browser
```

On Linux, Playwright may need operating-system dependencies; CI uses `pnpm exec playwright install --with-deps chromium`. Read that command's system-package prompt before running it on a personal machine.

The browser suite starts its own server on an available temporary port, stores reading data in a temporary directory, and uses the bundled demo plus generated PDF fixtures. It does not need a running daily reader. Reports, screenshots, and exports are written to ignored `test-results/`.

Optional environment variables:

| Variable | Purpose |
| --- | --- |
| `PAPER_READER_PYTHON` | Interpreter for the browser suite; defaults to `.venv/bin/python` |
| `PAPER_READER_BROWSER_CHANNEL` | `bundled` (CI/default), or a locally installed Playwright-supported channel such as `chrome` |
| `PAPER_READER_NODE_MODULES` | Use an external development dependency directory |
| `PAPER_READER_TEST_PDF` | Optional private local regression fixture; never required by public CI |

If you enable the optional private-PDF test, generated screenshots/reports may contain private material. Keep all `test-results/` files local; do not attach them automatically to an issue or PR.

For an interactive development session, use an isolated library:

```sh
.venv/bin/python server.py --port 0 --data-dir /absolute/path/to/a/temporary-reader-library
```

The server prints the assigned local URL. Choose a dedicated temporary directory, not your daily `data/` directory, when testing destructive operations.

## What GitHub Actions checks

The [Tests workflow](../.github/workflows/ci.yml) runs on pushes to `main`, pull requests, and manual dispatch:

| Check | Configured environment |
| --- | --- |
| Python unit/HTTP checks | Ubuntu 24.04 and macOS 15; Python 3.10 and 3.13 |
| Search checks | Ubuntu 24.04; Node 22 |
| Browser checks | Ubuntu 24.04; Python 3.13; Node 22; Playwright's bundled Chromium |

These are test targets, not a promise that every platform, browser, installation method, or sleep/wake scenario has been manually validated. A configured workflow is not evidence of a passing run; check the repository's Actions results and [validation record](VALIDATION.md).

The workflow has read-only repository permissions, cancels superseded runs, pins actions to verified commit SHAs, and uses synthetic fixtures. On failure it uploads a narrow selection of test reports for seven days; browser failure screenshots only contain synthetic CI fixtures. It does not upload the reading library, exports, backups, or an arbitrary private local fixture.

## Layout and dependency changes

- `server.py`: local HTTP API, reading records, and exports.
- `web/`: reading interface, selection/annotation rendering, and search.
- `scripts/`: asset preparation, optional macOS service management, and launch readiness.
- `tests/`: Python, search, and browser regression checks.
- `examples/`: redistributable, self-authored demo PDF.
- `assets-lock.json`: independent PDF.js version, archive URL, and integrity.

Dependabot checks Python, JavaScript development dependencies, and GitHub Actions weekly with a small open-PR limit. It does not update `assets-lock.json`; PDF.js updates remain a deliberate maintenance task. Dependency PRs do not merge automatically.

When updating PDF.js, verify the archive integrity against the intended upstream release, check the files listed in `scripts/setup.py`, update third-party notices as needed, and run real browser selection/zoom/export checks. Keep the source text, PDF coordinates, and original PDF bytes intact.
