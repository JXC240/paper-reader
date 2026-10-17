# Contributing to Paper Reader

Thank you for helping make sustained, original-language paper reading easier. Small, focused improvements are welcome: a reproducible bug, clearer instructions, a better reading interaction, or a regression check.

## Start with the reading problem

Open an issue describing the task you wanted to complete and what got in the way. For larger changes, discuss the workflow before building it. The project's focus is local reading, reliable annotations, portable notes, and bringing selected passages with context to an AI conversation.

Try the bundled demo before sharing a bug. Include the version or commit, operating system, browser, launch method, and minimal reproduction steps. Use synthetic text or a redistributable minimal PDF for unusual layouts; never upload a private paper or your reading library. Sensitive findings follow [SECURITY.md](SECURITY.md).

中文反馈和贡献同样欢迎。请描述具体阅读场景；问题截图优先使用自带示例，不上传私人论文或阅读记录。

## Make a focused change

1. Fork the repository and create a branch for one coherent improvement.
2. Follow [the development guide](docs/DEVELOPMENT.md) to prepare an isolated environment.
3. Preserve existing annotation formats and original PDF bytes. Explain any compatibility change and provide a migration/recovery path if needed.
4. Run the checks relevant to your change. Add a regression check when fixing behavior that could silently lose or misplace reading work.
5. Open a pull request describing the problem, resulting behavior, checks run, and remaining limitations. Use the bundled demo for screenshots.

Keep dependencies and abstractions proportionate to the task. Do not introduce cloud uploads, analytics, account requirements, or new network calls in the reading workflow without first discussing the user-facing effect. Do not edit generated assets in `vendor/` directly.

Be respectful and specific in discussions. Review the code and evidence, not the contributor. AI-assisted contributions are welcome; the contributor remains responsible for checking the result and stating what was tested.

## What must stay local

Do not commit `data/`, `exports/`, `.local/`, `.venv/`, `node_modules/`, `vendor/`, `test-results/`, personal configuration, access tokens, or private screenshots. Check staged files before submitting. The `.gitignore` file helps but is not a substitute for reviewing a diff.

Dependency updates must preserve the lock files and pass relevant checks. PDF.js is pinned separately in `assets-lock.json`; updating it requires checking the archive integrity, required files, rendering, selection coordinates, and exports. See [release checks](docs/RELEASING.md).
