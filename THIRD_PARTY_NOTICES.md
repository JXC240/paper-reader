# Third-party dependencies

The original application code and original demonstration PDF are licensed under MIT.
Third-party dependencies retain their own licenses and copyright notices.

| Dependency | Pinned version | License | Source |
| --- | --- | --- | --- |
| PDF.js / pdfjs-dist | 5.6.205 | Apache-2.0 | https://github.com/mozilla/pdf.js |
| pypdf | 6.10.0 | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| Playwright (developer tests only) | 1.62.1 | Apache-2.0 | https://github.com/microsoft/playwright |
| ReportLab (optional demo regeneration only) | Not required to run the app | BSD license | https://www.reportlab.com/ |

`scripts/setup.py` downloads the official npm PDF.js distribution using the URL
and SHA-512 integrity value in `assets-lock.json`. It retains the distribution's
`LICENSE` in `vendor/pdfjs/LICENSE`. Fonts, CMaps, and WASM files come from that
unmodified distribution and remain subject to its included notices.

pypdf and Playwright are installed through their package managers, retaining
their distribution license files. There are no runtime requests to a CDN, model
API, or third-party document service.

The original demo contains fictional reading instructions, not excerpts from a
published paper. Private papers, personal notes, and real-paper screenshots are
excluded from version control.
