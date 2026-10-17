# Releasing Paper Reader

This is the maintainer's release procedure. Publishing a GitHub Release is a deliberate action; the test workflow does not create tags, push code, or publish releases automatically.

## Prepare and verify

1. Review the complete diff and staged file list. Exclude personal PDFs, `data/`, exports, configuration, credentials, `.local/`, generated test artifacts, and local runtime/dependency directories.
2. Set the version consistently in `package.json`, the server's version header, README version references, and `CHANGELOG.md`. Do not move an existing published tag to a different commit.
3. Run the checks in [DEVELOPMENT.md](DEVELOPMENT.md). Check the GitHub Actions results for the exact candidate commit; record actual results and untested cases in [VALIDATION.md](VALIDATION.md).
4. Use a fresh checkout and the bundled demo to verify preparation, import, annotation, note persistence after reopening, and exports. Verify any changed backup/restore or upgrade path on an isolated library. Never use an old backup to overwrite the daily research library as a release test.
5. If macOS service handling changed, verify it on an explicitly selected test environment. Unit mocks do not prove login, reboot, or overnight sleep/wake behavior. Clearly state what was and was not exercised.
6. For a dependency change, review its upstream release notes and relevant browser/export checks. Keep exact runtime pins and lock files aligned. PDF.js has a separate `assets-lock.json` and requires a verified archive integrity value.

## Publish a version

After the candidate commit is pushed and its checks pass, create a new annotated tag on that commit, for example `v0.4.0` when releasing 0.4.0. Check the remote tag list first. Historical tags that exist only on one local development branch are not automatically tags for the public branch; do not repoint them as a shortcut.

Publish a GitHub Release from the new tag. Include:

- The user-visible changes and fixed reading/setup problems.
- Download and launch instructions, including Python and initial network requirements.
- Upgrade instructions and whether reading-data formats changed.
- Tested environments, known limitations, and any manual checks still outstanding.
- A link to the changelog and the checks for that commit.

GitHub's generated source ZIP/tar archives contain source code, not a packaged desktop application or a complete offline runtime. Do not describe them as a one-click installer. They must not include private data, prebuilt `.venv`, local browser binaries, or machine-specific background configuration.

## After publication

Open the release page and check that the tag, version text, source download, and links point to the intended commit. Try installation from the published source archive in a clean test directory. Keep earlier releases available and document any compatibility issue found after release rather than silently changing a tag.

Branch protection, required checks, private vulnerability reporting, and repository topics are GitHub settings, not features enabled by these files. Configure them separately when appropriate; do not claim they are active without verifying the repository settings.
