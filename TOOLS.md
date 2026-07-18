# Tool Registry

This is a conditional route card, not mandatory executor reading. Open it only when a
handoff requires a tool or before manually consuming a large/repetitive input. Read only
the relevant file under `tools/manifests/` for invocation details.

`planned` means unavailable: do not attempt it or let it block the task.

| Tool | Status | Use when |
|---|---|---|
| `repo-indexer` | planned | An authorized task needs compact architecture, symbol, call-site, or ownership discovery. Skip when the handoff already names the seam. |
| `test-failure-summarizer` | planned | Test/CI output is too large or noisy to inspect directly. |
| `change-risk-summarizer` | planned | A large authorized diff needs compact risk and test routing. |
| `size-report` | available | File sizes are needed without reading source contents. |
| `canvas-docs-scraper` | planned | Current official Canvas endpoint behavior must be verified. |
| `canvas-api-inspector` | planned | Authorized live/fixture Canvas data needs normalized object relationships. Never expose secrets or student data. |

Run the available size report from the repository root:

```powershell
py tools/size_report.py
```

Tool output should be compact and structured. Preserve source URLs, file paths, commands,
timestamps, and IDs only when they matter for review; keep credentials and student data
out of output. Use tools for retrieval, parsing, validation, summarization, and
normalization. Use reasoning for architecture, tradeoffs, review, and specifications.

Canvas-specific priority when a relevant tool becomes available:

- API documentation: `canvas-docs-scraper`
- Canvas objects and relationships: `canvas-api-inspector`
- unfamiliar local architecture: `repo-indexer`
- large test output: `test-failure-summarizer`
- large diffs: `change-risk-summarizer`

Tool use never widens the active handoff's file, data, or side-effect scope.
