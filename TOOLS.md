# Tool Registry

This registry helps agents decide when to use project-local tooling before spending LLM
context on large raw inputs. Tool manifests live in `tools/manifests/`.

Tools should return compact, structured output rather than large raw dumps. Preserve
source URLs, file paths, commands, timestamps, and IDs when they matter for review or
traceability.

## Choosing Tools

Check this file and `tools/manifests/` before brute-force reading of large docs, logs,
diffs, API responses, scraped HTML, or repeated repository searches.

Use tools for retrieval, parsing, validation, summarization, and normalization. Use LLM
reasoning for architecture, tradeoffs, planning, reviewing summarized output, and writing
specs.

## repo-indexer

Status: `planned`

Use when:

- Discovering local architecture
- Locating implementation points
- Finding call sites or imports
- Understanding project layout before making changes

Avoid when:

- The needed file or symbol is already known
- The task only requires reading one small file

Expected output:

- Compact map of files, symbols, routes, services, and tests
- Source file paths
- Relevant commands used

## test-failure-summarizer

Status: `planned`

Use when:

- Tests fail
- CI logs are large
- The user asks what broke
- Raw command output is too noisy for direct LLM inspection

Avoid when:

- The failure output is already short and specific
- The task is to design tests rather than inspect failures

Expected output:

- Failing command
- File and line when available
- Failure message
- Likely affected area

## change-risk-summarizer

Status: `planned`

Use when:

- Reviewing large changes
- Preparing PRs
- Deciding which tests to run
- Assessing behavioral risk

Avoid when:

- The diff is tiny and already visible
- The user asked for a specific file-level explanation

Expected output:

- Changed files
- Public API or schema changes
- Behavioral risk notes
- Suggested tests or checks

## canvas-docs-scraper

Status: `planned`

Use when:

- Canvas API behavior is needed
- Endpoint paths, params, auth, pagination, or response shapes are needed
- Current official documentation should be verified

Avoid when:

- The task only concerns local implementation
- The relevant official docs are already present in context

Expected output:

- Matching endpoints
- Required and optional params
- Response shape summary
- Source URLs
- Retrieval timestamp

## canvas-api-inspector

Status: `planned`

Use when:

- Course, module, assignment, quiz, rubric, user, or enrollment metadata is needed
- Relationships between Canvas objects matter
- Raw Canvas API responses are too large or noisy

Avoid when:

- Live Canvas access is not available and no fixture is supplied
- The task only needs static documentation

Expected output:

- Normalized JSON summary
- IDs, names, dates, and relationships
- Source endpoint or fixture path
- Retrieval timestamp when live data is used
