# Security policy

Paper Reader is an early-stage local application. It listens on the loopback interface and has no built-in account, cloud synchronization, or AI API. Installing dependencies requires network access; sending excerpts to an AI or another app is a separate user action.

## Reporting a concern

Check the repository's [Security page](https://github.com/JXC240/paper-reader/security) for **Report a vulnerability**. If GitHub private vulnerability reporting is available there, use it for sensitive details. This document does not imply that private reporting has been enabled or that a private contact channel is available.

If that option is absent, do not put exploit instructions, private PDFs, annotations, local paths, tokens, or personal data in a public issue. You may open a brief, sanitized issue asking the maintainer for a reporting channel, without disclosing the sensitive finding. Wait for a suitable channel before sending details. No response-time commitment is currently offered.

For an ordinary, non-sensitive bug, use the public bug-report template with the bundled demo or a synthetic reproduction.

中文：敏感问题优先使用仓库 Security 页面中实际可见的私密报告入口；如果没有，请先用不含敏感细节的 Issue 询问报告渠道。不要公开私人论文、阅读记录、令牌或可利用细节。

## Scope and updates

Reports should identify the affected version or commit and whether the current `main` reproduces the issue. Maintenance currently focuses on the current code and latest published version; older versions have no separate long-term support branch.

The application is designed for a single user's computer. Do not expose its port to a network or run it as a public multi-user service. Host, origin, and session-token checks reduce accidental cross-site access but do not make an arbitrary uploaded PDF trustworthy. Keep the browser, Python, and PDF-processing dependencies updated.

Before sharing diagnostic material, remove research content and identifying information. Maintainers and contributors should use synthetic fixtures for tests and review the contents of any generated report before sharing it.
