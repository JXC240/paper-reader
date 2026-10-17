# Usage, backup, and upgrades

[Home](../README.en.md) · [简体中文](USAGE.md) · [AI and Obsidian prompts](WORKFLOWS.en.md)

## Install and start

You need Python 3.10+. Extract the source ZIP to a separate folder, or use Git:

```sh
git clone https://github.com/JXC240/paper-reader.git
cd paper-reader
./start.sh
```

Setup creates the project's `.venv/`, installs the pinned pypdf dependency, and downloads verified PDF.js assets. Network access is used for setup and repairs. Everyday reading does not require Node.js or a model API key.

On macOS, double-click `启动阅读器.command` (“Start reader”). Open http://127.0.0.1:8877/ on the same computer and try the self-authored demo first. Leave the foreground terminal open; Control+C stops it.

- Missing Python: install Python 3.10+ and confirm `python3 --version` in a new terminal.
- Incomplete environment or failed download: follow the error and rerun `./start.sh --prepare-only`; keep certificate verification enabled.
- Occupied port: check whether the reader is already running. For an independent library, use `./start.sh --port 8878 --data-dir /absolute/path/separate-library`.
- Connection refused: check the foreground terminal or background service. Opening a browser page does not start Python.
- ZIP file permissions: use `sh start.sh` from the project folder. Review the source and use the normal macOS security process if the system blocks a launcher.

## Read beside a conversation

Use a desktop client that supports a local built-in browser, or a normal browser. Side-by-side display and local file access depend on the client and its permissions.

“复制论文链接” (“Copy paper link”) produces a URL with `?doc=<DOCUMENT_ID>`. Open it in another chat or tab using the same local library to keep that conversation on the intended paper. A missing explicit document produces an error rather than silently opening another paper. A link does not contain or publish the PDF.

“复制阅读卡点” (“Copy reading questions”) includes the paper ID, pages, original passages, nearby text, and saved notes. An assistant with authorized file access can use:

```text
<PROJECT>/data/documents/<DOCUMENT_ID>/record.json
<PROJECT>/data/documents/<DOCUMENT_ID>/reading.md
```

Replace `data/` with your actual library when using `--data-dir`. Global `current-reading.json` remains for older workflows, but document-specific records are the right reference for multiple conversations. Without file access, paste copied passages or share an export.

## Annotation and navigation

- Continuous marking is on by default. In select-first mode, choose text before deciding to mark or copy it.
- Seven colors combine with highlights, underlines, and strikeouts. Existing cards can be restyled, deleted, or classified as vocabulary.
- Vocabulary classification is explicit; a highlight does not automatically mean an unfamiliar word.
- Typed notes show a draft state and stay through zoom, navigation, and filtering. If browser storage is available, drafts can also recover after reload. Click “保存笔记” (“Save note”) to put them in the reading library. Unsaved drafts are not included in exports or library backups, and clearing browser data can remove them.
- The page's “使用说明” (“Help”) lists keyboard navigation. Reading shortcuts leave text inputs alone.
- Zoom accepts 25%–400%, including decimals. Cmd/Ctrl +, −, and 0 zoom in, zoom out, and fit width.
- Cmd/Ctrl F searches text; Enter/Shift Enter moves between results. Orange result boxes are temporary, not saved annotations.
- Escape or a blank click cancels a selection. Scrolling dismisses the floating selection menu.
- The outline comes from the PDF. Page bookmarks can be named.
- Markdown exports work as portable notes; annotated PDFs are separate copies.

## Optional macOS background service

1. Save notes and wait for “已保存到本机” (“Saved locally”). Stop a foreground service with Control+C.
2. Double-click `安装后台服务.command` (“Install background service”).
3. Open the local address for daily reading. `启动阅读器.command` reuses or re-enables the installed service.

| Action | Launcher |
| --- | --- |
| Install login service | `安装后台服务.command` |
| Stop and disable automatic startup | `停止后台服务.command` |
| Re-enable | `启动阅读器.command` |
| Remove the service, preserve reading data | `卸载后台服务.command` |

No administrator access is needed. Configuration is at `~/Library/LaunchAgents/local.paper-reader.plist`; logs are in `~/Library/Logs/PaperReader/`. Uninstall before moving the project and reinstall afterwards. This does not change power settings. Actual overnight sleep, login, and reboot behavior still need use-based validation; restart handling is not a substitute for backups.

## Backup and recovery

Save notes first, wait for the saved status, and click “备份阅读库” (“Back up library”). The ZIP includes imported PDFs, saved annotations, notes, bookmarks, reading positions, and a verification manifest. Browser drafts, runtime dependencies, and regenerable exports are excluded.

Keep these private archives out of public repositories. Copying the entire `data/` directory is another option; stop the service first for a consistent offline copy.

Built-in backups support up to 1 GiB uncompressed and 3,000 documents. Larger libraries produce an explicit error; use an offline copy of the full data directory instead. Recovery on Windows has not been verified.

Restore to a directory that does not exist yet:

```sh
.venv/bin/python scripts/library_backup.py restore /absolute/path/paper-reader-backup.zip --to /absolute/path/reader-restored
./start.sh --port 8878 --data-dir /absolute/path/reader-restored
```

Recovery validates paths, the manifest, hashes, and records before installing the restored library. It does not merge into or overwrite a live library. Open http://127.0.0.1:8878/ and verify document count, annotations, notes, bookmarks, and exports. Keep the old library until you explicitly switch. The default macOS background configuration still uses the project's `data/`, not this separate directory.

An unreadable record is reported while readable papers remain available; the damaged record is preserved. Full backup reports an error if a record cannot be verified rather than silently creating an incomplete archive.

## Upgrade safely

1. Save notes, create a backup, and verify recovery.
2. Stop the service: Control+C in foreground mode or `停止后台服务.command` (“Stop background service”).
3. For Git installations, check local changes and the intended branch, then use `git pull --ff-only`. For ZIP installations, extract to a new directory and preserve the old project and library. Uninstall an old background service before moving its project.
4. Run **`./start.sh --prepare-only`** to prepare updated dependencies. Simply opening an installed background service can reuse its environment and does not replace this step.
5. Start the updated reader, refresh the page, and verify your saved work. Reinstall the background service if you moved to a new project directory.

Source updates do not automatically roll back personal records. Test old code with an independent library copy instead of overwriting your live data.

## Data layout

```text
data/
  documents/<PDF_SHA256>/
    original.pdf
    record.json
    reading.md
  active.json
  current-reading.json
  current-reading.md
  exports/
```

Importing identical PDF bytes under another name reuses the record. Changed contents create another document. Git ignores personal libraries, but always inspect archives before publishing them.

## Report a problem

Include your OS, Python version, startup mode, reproduction steps, expected behavior, and the error text. Prefer the demo PDF. Remove personal paths, tokens, papers, records, and backup files.

[Issues](https://github.com/JXC240/paper-reader/issues/new/choose) · [Validation scope](VALIDATION.md)
