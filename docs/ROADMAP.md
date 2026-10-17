# Roadmap · 项目路线

Paper Reader supports a deliberate reading workflow: read the original, mark a question, discuss it in context, and return to the source. Learning outcomes require reader feedback and are not inferred from feature delivery.

## Current iteration · v0.4.0

- Protect unsaved note drafts and make their state visible.
- Bind each browser/chat to an explicit document link and record.
- Make activation atomic and isolate corrupt library entries.
- Add full-library backup and recovery to a new directory.
- Run Python, search, and browser checks on GitHub.
- Add contribution, issue, security, development, and release guidance.
- Simplify the bilingual homepage and provide a current self-authored demo screenshot.

Implementation and test evidence: [Changelog](../CHANGELOG.md), [Validation](VALIDATION.md). A listed feature does not imply all platforms or all failure modes have been tested.

## Next candidates · 待反馈后选择

These are ideas, not committed dates:

- Continuous scrolling and multi-step undo/redo.
- English interface and English launcher names.
- Annotation labels for questions, methods, and conclusions.
- A smoother upgrade and migration interface.
- Reading-library organization and large-document performance baselines.
- Optional review material built from explicitly confirmed reading notes.
- Keyboard-only and screen-reader walkthroughs.

## Evidence we want · 希望获得的验证

Ask new readers to independently install, annotate, reopen, export, back up, restore, and upgrade without maintainer intervention. Record macOS sleep/wake and login behavior over actual daily use. Test long and image-heavy PDFs before making performance claims.

Windows support and an installable desktop bundle require their own implementation and real-platform validation. Contribution ideas are welcome through [Issues](https://github.com/JXC240/paper-reader/issues/new/choose).
