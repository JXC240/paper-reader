[Home](../README.en.md) · [简体中文](WORKFLOWS.md) · [Usage](USAGE.en.md)

# AI reading, Obsidian, and weekly review

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

If you have authorized local file access, read the document-specific data/documents/<DOCUMENT_ID>/record.json that I provide
and verify the document name and annotations. Use “复制论文链接” (Copy paper link)
to keep this conversation on the same paper; do not rely only on global current-reading.json. Otherwise, I will paste the copied reading passages;
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
