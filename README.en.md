# Paper Reader

[简体中文](README.md) | English

**Let AI read with you. Keep the thinking yours.**

A local PDF reading companion for people who want to get better at reading research papers in English—not just get through another translation. Read a passage yourself, mark what needs attention, and bring the original sentence into a conversation with AI.

**Read first → Annotate → Discuss with AI → Return to the original → Review over time**

![Paper Reader displaying a self-authored example PDF with annotations](docs/images/reader.png)

*Screenshot from an earlier build, using the project's own example document. The current interface is in Chinese.*

## Why Paper Reader exists

This project began with a simple frustration: **I wanted to read an English paper beside my GPT conversation, but the built-in PDF viewer did not give me the annotation workflow I needed.**

An unfamiliar phrase. A sentence with too many clauses. A method worth revisiting. I wanted to mark these moments as I read, without turning every highlight into a written question or repeatedly switching windows to copy text and reconstruct its context.

The longer-term goal matters even more: becoming comfortable reading the original English. Following a sentence's structure, recognizing academic expressions, and understanding how an author builds an argument are skills developed through practice. A Chinese translation can help, but receiving one is not the same as learning to read the source.

Paper Reader makes room for that practice: **try first, ask when you need help, then return to the English and read it again.** With optional notes in Obsidian and regular review, today's difficult sentence can become something you recognize next time.

This is the project's learning philosophy, not a measured learning outcome. Using the tool, saving a note, or reading an AI explanation does not demonstrate mastery.

## A reading workflow that stays yours

1. **Try a short passage yourself.** Identify its main point or the exact place where you get stuck.
2. **Mark it without breaking your rhythm.** Highlight, underline, or strike through a passage; a comment is optional.
3. **Ask with the original in view.** Discuss the complete sentence and its context, not an isolated list of highlighted words.
4. **Return to the paper.** Read the English again and explain it in your own words.
5. **Keep what is worth practicing.** If you choose, ask an authorized assistant to organize selected vocabulary, expressions, and sentence patterns in Obsidian, then review them weekly.

Use this for close reading or quick screening. You do not have to read every paper word by word. A highlight means “pay attention here,” not necessarily “new vocabulary,” and certainly not “already learned.”

## What is included

| Reading need | What Paper Reader provides |
| --- | --- |
| Mark as you read | Continuous marking or select-first mode; seven colors; highlights, underlines, and strikeouts |
| Pick up where you left off | Persistent annotations and notes, page and zoom restoration, and approximate within-page reading position |
| Find your way around | Full-text search, the PDF's embedded outline, and named page bookmarks |
| Bring a question into a chat | Selected text, PDF page number, coordinates, and nearby source text; copy passages or export Markdown |
| Keep a portable record | Optional notes and explicit vocabulary flags; Markdown and a separate PDF with standard annotations |
| Read regularly on a Mac | Optional login background service, restart-on-exit behavior, logs, and stop/uninstall launchers |

Yellow, green, pink, blue, purple, orange, and red are available for all three annotation styles. You can change a saved annotation's style or color later. Striking out text does not delete it or establish that the paper is wrong.

**No built-in model. No model API key required.** Paper Reader handles the document and your reading record. AI explanations happen in the chat tool you choose; they are not generated inside the reader.

## Get started

You need **Python 3.10 or newer**. Initial setup downloads the pinned dependencies and PDF.js assets. Once setup is complete, reading and saving work offline; an AI conversation has its own connection requirements.

### 1. Download and start

Download this repository as a ZIP and extract it, or clone it with Git.

On **macOS**, double-click **`启动阅读器.command`** (“Start Reader”). It prepares a project-specific Python environment and opens the reader. Alternatively, run this from the project directory:

```sh
./start.sh
```

Open **[http://127.0.0.1:8877/](http://127.0.0.1:8877/)**. Try **“试试示例 PDF”** (“Try the example PDF”) before importing a paper.

The default foreground mode needs its terminal window to remain open. Press **Control+C** there to stop it. Background running on macOS is optional; downloading the project does not install a login item.

**Platform status:** macOS is the primary tested platform. Linux can use `start.sh`, but has not received full platform validation. Windows is not fully tested and does not have a verified one-click setup. The reader's UI and most supporting project documents are currently in Chinese.

### 2. Put the paper beside your conversation

In a supported **ChatGPT desktop app**, open the local address in its built-in browser and use split view to keep the paper beside your chat. The reader also works independently in a normal browser. See [OpenAI's browser documentation](https://learn.chatgpt.com/docs/browser) for built-in browser, `@Browser`, and split-view controls.

Use a browser **on the same computer that is running Paper Reader**. `127.0.0.1` refers to that browser's own device; it is not a public website. A phone, another computer, or a cloud browser cannot reach your reader simply by opening this address. Client availability and permissions can differ.

You can use a different conversation without moving the reader: keep the local service running, then open the same address beside the other chat.

### 3. Read, mark, then discuss

Click **“打开 PDF”** (“Open PDF”) and choose a document. Continuous marking is on by default: selecting text saves an annotation. Switch to select-first mode if you want to decide whether to mark or copy each selection.

- **Assistant with authorized local file access:** ask it to read `data/current-reading.json` in your Paper Reader directory for the current document, annotations, and nearby text.
- **Assistant without local file access:** click **“复制阅读卡点”** (“Copy reading questions”) and paste the result into your chat, or export Markdown and share it yourself.

Opening the reader does **not** automatically send selected text to AI. Creating an annotation does **not** automatically trigger an explanation.

## Copy-ready prompts

These are templates, not actions already performed. Replace the values in angle brackets. Installation and file writing require a capable assistant with the relevant permissions; otherwise, ask for manual steps or ready-to-save Markdown.

### 1. Ask an assistant to install Paper Reader

Use this with a desktop assistant that can work on your computer:

```text
Please install and run Paper Reader on my computer.
Repository: https://github.com/JXC240/paper-reader

First check my operating system, Python installation, and the repository README.
Review the setup scripts and dependencies before running them.
Use a suitable, separate project directory and tell me its actual location.
Do not overwrite an existing project or any reading data.

Use the project's own Python environment, not my global Python installation.
Do not disable certificate verification or expose the server to the public internet.
Prepare the dependencies, start the reader, and verify that the local page loads.
If the port is occupied, identify the program first; do not kill unrelated processes.
Explain the optional macOS login background service and ask before installing it.

Tell me how to start, stop, and back up the reader.
If you cannot execute local actions, give me manual instructions instead of claiming
that installation is complete.
```

### 2. Open the reader beside this GPT conversation

Start the local service first, and use a desktop client with a local built-in browser:

```text
Please use this desktop app's built-in browser (@Browser) to open:
http://127.0.0.1:8877/

This is Paper Reader running on this computer. Keep the current conversation and,
if supported, show the chat and reader side by side.
Verify that the reader actually loads; opening a tab alone is not confirmation.
If the connection is refused, check whether the local service is running.
Do not assume that this requires uploading my papers or deploying a public website.
If local browser access is unavailable here, explain the limitation and show me how
to open the reader in a normal browser on this computer.
```

### 3. Read with me; do not skip my attempt to understand

```text
I am reading an English research paper in Paper Reader and want to practice
understanding the original English over time.
Paper Reader directory: <ABSOLUTE_PATH_TO_PAPER_READER>

If you have authorized local file access, read data/current-reading.json and check
the document and annotations. Otherwise, I will paste the copied reading passages;
do not pretend you have accessed my files.

Starting where I specify, follow the original order, one complete sentence at a time.
First let me try to explain the meaning or identify what confuses me.
Then provide the English original, a faithful full-sentence Chinese translation,
meaningful chunks, important collocations, and the main clause and modifiers.
Use the surrounding argument to explain the sentence, not just dictionary meanings
for highlighted words. Connect to earlier sentences when needed.

Check formulas, numbers, and scientific claims against the PDF; label uncertainty.
After explaining, ask me to reread the English and paraphrase it in my own words.
Do not treat an explanation you gave as a skill I have mastered.
Discuss in the chat first. Only archive vocabulary or notes that I explicitly confirm.
```

The translation language in this template is Chinese; change it to your preferred language.

### 4. Save confirmed learning notes in Obsidian

Obsidian is optional. This is a workflow for an assistant **you authorize**, not automatic synchronization built into Paper Reader. Local file access depends on the client and its permissions; see [OpenAI's local access documentation](https://learn.chatgpt.com/docs/enterprise/chatgpt-work-local-security).

```text
Please organize only the vocabulary, academic expressions, and difficult sentences
that I explicitly confirmed for archiving during this reading session.
Obsidian vault: <ABSOLUTE_PATH_TO_MY_VAULT>
Target folder within the vault: <PAPER_ENGLISH_FOLDER>
Paper Reader directory: <ABSOLUTE_PATH_TO_PAPER_READER>

Inspect the existing notes first. Follow their structure and avoid duplicates.
Keep research-paper English separate from fiction or everyday English notes.
For each entry, retain the original sentence, paper title, verifiable PDF page,
date, faithful Chinese translation, meaning or collocation, and my specific question.
Clearly separate the paper's text from AI explanations. Do not invent missing sources
or label an explained item as mastered.

Append or update only relevant entries. Do not delete unrelated notes, overwrite old
notes, or modify the original PDF.
Verify the saved result and report the actual file paths.
If you cannot write to the vault, provide ready-to-save Markdown and clearly state
that it has not been written or synchronized.
```

### 5. Turn this week's notes into active reading practice

This prompt starts a **manual weekly review**, not a scheduled task:

```text
Please help me review the research-paper English notes actually saved this week.
Obsidian vault: <ABSOLUTE_PATH_TO_MY_VAULT>
Paper-English folder: <FOLDER_WITHIN_VAULT>
Date range: <START_DATE_TO_END_DATE>

Check the real notes and sources first; do not invent reading I did not do.
Group the material into vocabulary and collocations, sentence structure,
academic expressions, and unresolved questions. Include a source list.

Start with a short quiz: recall an original sentence, choose a meaning in context,
identify the main clause, and paraphrase a sentence. Do not show the answers yet.
Wait for my responses before checking and explaining them.
Distinguish saved, reviewed, correct this time, and still needs practice;
do not automatically declare mastery.

Follow the existing note structure when saving the review, preserve unrelated notes,
and report the actual saved paths. Without file access, provide Markdown instead.
Based on my responses, suggest a few expressions to practice next week.
Keep these as suggestions, not plans I have already agreed to.
```

For an automatic weekly review, separately ask your assistant to create or update a scheduled task and confirm the time, time zone, execution environment, and vault access. A written prompt does not establish that a scheduler is active. Sleeping or disconnected computers may make local notes unavailable; manual review remains an option.

## Optional macOS background service

To use the reader without keeping a terminal window open:

1. If a foreground reader is running, wait for **“已保存到本机”** (“Saved locally”), then stop it with Control+C in its terminal.
2. Double-click **`安装后台服务.command`** (“Install background service”). It prepares the environment and installs a service for the current macOS user. It will not terminate an unrelated program using the port.
3. Open the local address whenever you want to read. **`启动阅读器.command`** also reuses an installed background service.

| Action | Launcher and behavior |
| --- | --- |
| Install | `安装后台服务.command`: start at login and restart if the service exits |
| Stop | `停止后台服务.command`: stop and disable automatic startup; keep configuration and data |
| Start again | `启动阅读器.command`: re-enable an installed background service |
| Uninstall | `卸载后台服务.command`: remove this project's background item; retain reading data, logs, and a configuration backup |

No administrator privileges are needed. The server listens only on `127.0.0.1:8877`. Its configuration is at `~/Library/LaunchAgents/local.paper-reader.plist`; logs are under `~/Library/Logs/PaperReader/`.

This does not change sleep or lid-close settings and does not promise service availability while the Mac sleeps. Automatic restart has been tested locally; an actual overnight sleep/wake cycle and login cycle still need further validation. Uninstall the service before moving the project directory, then reinstall it afterward. Restart protection is not a substitute for backups.

## Everyday controls

- **Zoom:** enter any value from 25% to 400%, including decimals. The −/+ buttons change zoom by 10 percentage points. ⌘/Ctrl +, −, and 0 zoom in, zoom out, and fit to width.
- **Search:** ⌘/Ctrl F opens search. Matches ignore case and normalize whitespace, with a maximum of 500 results. Enter/Shift+Enter moves forward/backward. Orange search outlines are temporary, not saved annotations.
- **Dismiss a selection:** click blank space, press Esc, scroll, or close the floating menu with ×.
- **Edit a mark:** use its sidebar card to change color/style, add a note, or explicitly flag it as vocabulary. Delete and single-step undo are available.
- **Navigate:** “导航” (“Navigation”) shows the embedded PDF outline and named page bookmarks. No embedded outline means no outline; the app does not invent one with AI.
- **Save and export:** wait for “已保存到本机” (“Saved locally”). Export Markdown for portable notes or an annotated PDF copy. The original PDF is not overwritten.

## Your data, privacy, and backups

```text
data/
  documents/<SHA-256-of-PDF-content>/
    original.pdf          # imported copy of the PDF
    record.json           # annotations, context, notes, bookmarks, reading position
  current-reading.json    # local entry point for the current reading record
  current-reading.md      # human-readable snapshot
  exports/                # exported Markdown and annotated copies
```

Back up the entire `data/` directory to retain your papers and reading records. Importing identical PDF bytes under another filename reuses the record; changed file contents identify a different document. Git versions cover source code, not private reading data, so checking out old code does not roll back your annotations.

Paper Reader saves PDFs and annotations locally and does not itself upload them to a model or cloud service. **If you paste passages into AI or authorize an assistant to read files, relevant content enters that AI workflow and is subject to its data policies.** Local execution does not imply device-only model inference. See [OpenAI's local data handling guidance](https://learn.chatgpt.com/docs/enterprise/chatgpt-work-local-security).

Private PDFs, annotations, exports, environments, logs, and machine-specific configuration are excluded from Git by default. The public example PDF is self-authored. Still review staged files before publishing; do not upload a ZIP of your entire working directory.

## Current limits

- This is a **local web application**, not an official ChatGPT plugin or a Chrome extension. Side-by-side use depends on your desktop client's capabilities.
- There is no built-in AI chat, automatic message sending, Obsidian synchronization, or weekly-review scheduler. The prompts above connect separate tools with the appropriate permissions.
- Reading is page by page. There is no continuous scrolling, scanned-document OCR, single selection across pages, figure-region selection, or multi-step undo/redo.
- Search requires extractable PDF text. Columns, hyphenation, ligatures, and formulas may affect extraction and reading order. Verify source context, translations, and scientific conclusions against the PDF.
- Existing PDF annotations remain visible and are preserved in exports; the sidebar manages annotations created in Paper Reader, not imported legacy annotations.
- Reading-position restoration uses a relative viewport anchor and is approximate, especially near page edges or after layout changes.
- macOS has received the most testing; full Linux, Windows, and other-client compatibility is not established.

## Development and license

Current application version: **v0.3.1**. This adds optional macOS background management and recovery from an expired page session after service restart to v0.3.0's search, outline, bookmarks, and reading-position support.

GitHub history starts with the initial source publication. Earlier development history and six version tags remain in the maintainer's local repository; earlier milestones are documented in the changelog.

[Mozilla PDF.js](https://github.com/mozilla/pdf.js) renders pages and text; [pypdf](https://github.com/py-pdf/pypdf) exports standard PDF annotations. A local Python server saves records atomically. Dependencies are pinned, and normal use does not require Node.js. Original project code is under the [MIT License](LICENSE); see [third-party notices](THIRD_PARTY_NOTICES.md) for dependency licensing.

```sh
# Python unit and HTTP tests use temporary data directories.
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v

# Search utility tests require Node.js, but no npm dependencies.
node --test tests/search.mjs

# Browser checks require development dependencies and a test browser.
npm install
npx playwright install chromium
npm run test:browser
```

A `pnpm-lock.yaml` is included if you prefer pnpm. Browser checks use an isolated temporary library. Set `PAPER_READER_BROWSER_CHANNEL=chrome` to use installed Chrome, or `PAPER_READER_TEST_PDF` to include a local paper in regression checks. Do not commit private papers or their test screenshots.

See the [validation record](docs/VALIDATION.md), [changelog](CHANGELOG.md), and [project plan](PLAN.md) for test scope, milestones, and design intent. These supporting documents are currently in Chinese. Passing software tests is not evidence of improved reading ability.

The project grew from a reader's needs and hands-on feedback, with AI-assisted implementation. Contributions and specific reading scenarios are welcome—please include reproducible steps and examples that do not expose private or copyrighted papers.

**Keep the paper close. Keep asking questions. Keep practicing.**
