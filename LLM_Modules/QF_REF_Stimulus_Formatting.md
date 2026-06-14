# QuizForge Stimulus Formatting Reference
**Last Updated:** 2025-12-09  
**Purpose:** Technical reference for how QuizForge's engine processes prose, poetry, code, and other stimulus content types.

---

## Overview

QuizForge's rendering pipeline (`engine/rendering/canvas/html_formatter.py`) automatically detects and formats different content types within stimulus items and question prompts. Understanding these behaviors is critical for LLM authoring modules (Base, FullStack) to produce compatible output.

---

## Content Type Detection & Processing

### 1. **Code Blocks**

#### Markdown Fences → HTML Conversion
Canvas New Quizzes **does NOT support Markdown fenced code blocks**. QuizForge converts:

```
```python
def hello():
    print("Hello")
```
```

**Becomes:**
```html
<pre style="background-color: #272822; color: #F8F8F2; padding: 10px; border-radius: 4px; font-family: 'Courier New', Consolas, monospace; overflow-x: auto; line-height: 1.5; white-space: pre; display: block;">
<code class="language-python">[syntax-highlighted HTML]</code>
</pre>
```

#### Supported Fence Types
- ` ```python ` — Python code (syntax highlighted with Monokai theme)
- ` ```javascript ` — JavaScript code (escaped, not highlighted)
- ` ```code ` — Generic code (escaped, no highlighting)
- ` ```excerpt ` — Treated as prose passage with paragraph numbering
- ` ```prose ` — Forced prose rendering (paragraph numbering)
- ` ```poetry ` — Forced poetry rendering (line numbering)

#### Inline Code
- Backticks: `` `variable` `` → `<code>variable</code>`
- Automatically escaped for HTML safety

#### Key Implementation Details
- **Function:** `transform_code_blocks(text: str) -> str`
- **Escape Handling:** Uses `xml_escape()` for non-highlighted code
- **Newline Cleaning:** Converts JSON-escaped `\\n` → actual newlines before rendering
- **Python Highlighting:** Monokai-style with keyword/function/string/comment colors

---

### 2. **Prose (Paragraph-Based Content)**

#### Auto-Detection
QuizForge analyzes content to determine if it's prose using these heuristics:
- Average line length > 60 characters → prose score +0.2
- Multiple paragraph breaks (`\n\n` >= 3) → prose score +0.4
- High sentences-per-line ratio (>0.5) → prose score +0.2
- Inconsistent line lengths (std dev > 70% of mean) → prose score +0.2

#### Rendering Behavior
- **Paragraph Numbering:** Each `\n\n`-separated block gets `{PARANUM:N}` marker
- **HTML Output:**
  ```html
  <div style="margin:10px 0;">
    <div style="font-family: inherit; font-size:0.95em; padding:14px 18px; background:#fff; border:1px solid #d9d9d9; border-left:5px solid #4b79ff; line-height:1.6;">
      <p style="margin: 0 0 0.9em 0; line-height: 1.6;">[1] First paragraph...</p>
      <p style="margin: 0 0 0.9em 0; line-height: 1.6;">[2] Second paragraph...</p>
    </div>
  </div>
  ```
- **Number Style:** `font-size: 0.85em; font-style: italic; color: #999; font-weight: normal;`

#### Forced Prose Rendering
Use fences to override auto-detection:
```
```prose
This will always be treated as prose,
regardless of line length or structure.
```
```

---

### 3. **Poetry (Line-Based Content)**

#### Auto-Detection
QuizForge identifies poetry using these signals:
- Short average line length (<60 chars) → poetry score +0.3
- No paragraph breaks (`\n\n` == 0) → poetry score +0.2
- Low sentences-per-line ratio (<0.5) → poetry score +0.3
- Consistent line lengths (std dev < 30% of mean) → poetry score +0.4
- Multiple stanza breaks (consecutive empty lines) → poetry score +0.2 per break (max +0.4)
- High capitalized line starts (>80%) → poetry score +0.2

#### Rendering Behavior
- **Line Numbering:** Every 5th line and line 1 get `{LINENUM:N}` markers (right-padded)
- **HTML Output:**
  ```html
  <div style="margin:10px 0;">
    <div style="font-family: inherit; font-size:0.95em; padding:14px 18px; background:#fff; border:1px solid #d9d9d9; border-left:5px solid #4b79ff; line-height:1.6;">
      <div style="margin: 0; padding: 0; line-height: 1.6;"> 1      Two roads diverged...</div>
      <div style="margin: 0; padding: 0; line-height: 1.6;">        And sorry I could not...</div>
      <div style="margin: 0; padding: 0; line-height: 1.6;">&nbsp;</div>
      <div style="margin: 0; padding: 0; line-height: 1.6;"> 5      I took the one...</div>
    </div>
  </div>
  ```
- **Blank Lines:** Rendered as `<div>&nbsp;</div>` to preserve stanza breaks

#### Forced Poetry Rendering
Use fences to override auto-detection:
```
```poetry
Roses are red,
Violets are blue,
This will render
As poetry for you.
```
```

#### **CRITICAL:** Never convert poetry to prose. Always preserve line breaks and indentation.

---

### 4. **Excerpt Blocks (Legacy/Special Syntax)**

#### Triple-Angle Bracket Syntax
```
>>>
This content will be auto-detected and numbered.
>>>
```

**Behavior:** Content between `>>>` markers is passed to `add_passage_numbering()` with `passage_type="auto"`, which runs the prose vs. poetry detection algorithm.

#### When Used
- Primarily for backward compatibility with legacy QuizForge quizzes
- Prefer using explicit fences (` ```prose ` or ` ```poetry `) for clarity

---

## JSON String Escaping Rules (Critical for LLM Authoring)

### When Embedding Content in JSON

**Problem:** JSON requires double quotes to be escaped, but raw content (code, passages) often contains quotes.

**Solution:** Escape inner quotes with backslash:
```json
{
  "prompt": "What does this code do?\n\n```python\npassword = \"SECRET\"\nprint(\"Hello\")\n```"
}
```

**Key Escaping Rules:**
1. **Inner double quotes:** `"` → `\"`
2. **Newlines in JSON strings:** Explicit `\n` (not actual line breaks)
3. **Backslashes in code:** `\` → `\\` (if not already escaped)
4. **Triple backticks:** Safe to use in JSON strings (no escaping needed)

**Example (Python code in JSON):**
```json
{
  "prompt": "```python\ndef greet(name):\n    print(f\"Hello, {name}!\")\n```\n\nWhat does this function do?"
}
```

**After JSON parsing, QuizForge's pipeline will:**
1. Convert `\n` to actual newlines
2. Detect ` ```python ` fence
3. Extract code content
4. Apply syntax highlighting
5. Wrap in `<pre><code>` with Monokai styling

---

## Stimulus Layout Options

### STIMULUS Item Fields
- `id` (required): Unique identifier for child question references
- `prompt`: Content (can be empty, but context text preferred)
- `format`: `"text"` | `"code"` | `"markdown"` (optional, informational only)
- `layout`: `"below"` (default) | `"right"` (side-by-side)
- `assets`: List of `{ "type": "image|table|audio|video|data", "uri": "...", "alt_text": "..." }`

### Layout Behavior
- **`"below"` (default):** Stimulus renders above child questions (vertical stacking). Safer for screen readers and mobile viewports.
- **`"right"` (side-by-side):** Stimulus appears alongside questions. Use only for longer passages where comparison helps; requires wider viewport.

### Best Practices
- **Limit child questions to 2–4 per stimulus.** More creates cramped formatting.
- **Default to `"below"` layout** unless teacher explicitly requests side-by-side.
- **Provide context text even if `prompt` can be empty.** Empty stimuli are structural markers; students benefit from explicit content.

---

## Newline Handling Pipeline

### JSON → Python → HTML Flow

1. **LLM Authoring (JSON):**
   ```json
   "prompt": "Line 1\nLine 2\nLine 3"
   ```

2. **JSON Parsing (Python `json.loads`):**
   - Converts `\n` escape sequences to actual newline characters (`chr(10)`)

3. **QuizForge Processing:**
   - `_clean_text_content()` handles any remaining `\\n` (double-escaped) → `\n` → actual newline
   - `htmlize_prompt()` splits on `\n` for fence/block detection

4. **HTML Rendering:**
   - Code blocks: Newlines preserved in `<pre>` tags (white-space: pre)
   - Poetry: Each line becomes a `<div>` (newlines become structure)
   - Prose: Paragraphs split on `\n\n` (single `\n` within paragraph preserved if needed)

**Key Takeaway:** Use explicit `\n` in JSON strings. QuizForge's pipeline will convert them to proper newlines before rendering.

---

## Auto-Detection Confidence Thresholds

### `add_passage_numbering()` Logic

```python
if passage_type == "auto":
    detected_type, confidence = _analyze_passage_content(text, lines)
    passage_type = detected_type if confidence > 0.6 else "prose"  # Conservative fallback
```

**Interpretation:**
- **Confidence > 0.6:** Use detected type (poetry or prose)
- **Confidence ≤ 0.6:** Default to prose (safer for readability)

**Why Conservative?**
- Misidentifying prose as poetry creates awkward line numbering
- Prose rendering is more forgiving of mixed content

---

## Practical Guidance for LLM Modules

### For QuizForge_Base.md (JSON Output)
1. **Fences in JSON strings:** Use explicit `\n` for newlines:
   ```json
   "prompt": "```python\nfor i in range(5):\n    print(i)\n```"
   ```
2. **Escape inner quotes:** Code with strings requires `\"`:
   ```json
   "prompt": "```python\nprint(\"Hello, World!\")\n```"
   ```
3. **Poetry preservation:** Never collapse line breaks; maintain original structure:
   ```json
   "prompt": "```poetry\nTwo roads diverged in a yellow wood,\nAnd sorry I could not travel both\n```"
   ```

### For QuizForge_FullStack_Complete.md (QTI XML Output)
1. **HTML escaping in QTI:** Canvas expects escaped HTML in XML:
   ```xml
   <mattext texttype="text/html">&lt;pre&gt;&lt;code&gt;...&lt;/code&gt;&lt;/pre&gt;</mattext>
   ```
2. **Prose/poetry rendering:** Generate HTML directly (with numbering logic if desired):
   ```xml
   <mattext texttype="text/html">&lt;div style="..."&gt;&lt;p&gt;[1] Paragraph...&lt;/p&gt;&lt;/div&gt;</mattext>
   ```
3. **Code blocks:** Use Monokai-style `<pre><code>` with inline CSS.

---

## Common Pitfalls & Anti-Patterns

### ❌ **Don't:** Mix prose and poetry in one stimulus without fences
**Why:** Auto-detection may misclassify; explicit fences clarify intent.

### ❌ **Don't:** Use raw Markdown code blocks in Canvas output
**Why:** Canvas New Quizzes doesn't render them; they appear as literal backticks.

### ❌ **Don't:** Strip newlines from poetry or code
**Why:** Formatting is semantically critical; line breaks convey structure.

### ❌ **Don't:** Forget to escape JSON inner quotes
**Why:** Causes JSON parse errors; quiz will fail to import.

### ✅ **Do:** Use explicit fences when content type is ambiguous
**Example:**
```
```prose
This short passage might look like poetry,
but it's actually prose.
```
```

### ✅ **Do:** Preserve indentation in code blocks
**Example:**
```
```python
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)
```
```

### ✅ **Do:** Use `\n` explicitly in JSON strings
**Example:**
```json
"prompt": "First line\nSecond line\nThird line"
```

---

## Testing & Validation

### Manual Checks (Pre-Output)
1. **JSON validity:** All inner quotes escaped? No trailing commas?
2. **Fence matching:** Every ` ``` ` opener has a closer?
3. **Newline consistency:** Code/poetry has explicit `\n` in JSON strings?
4. **Content type:** Prose vs. poetry correctly identified or forced with fences?

### QuizForge Pipeline Validation
- **Orchestrator:** Parses JSON and validates schema
- **html_formatter.py:** Logs warnings if backticks remain after transformation
- **QTI Builder:** Ensures mattext elements are properly escaped

---

## Summary: Key Rules for LLM Authoring

| Content Type | JSON Syntax | Rendering | Numbering |
|--------------|-------------|-----------|-----------|
| **Code (Python)** | ` ```python\ncode\n``` ` | `<pre><code>` + Monokai | None |
| **Code (Other)** | ` ```lang\ncode\n``` ` | `<pre><code>` escaped | None |
| **Prose** | ` ```prose\ntext\n``` ` or auto | `<p>` tags + border/padding | Paragraph [N] |
| **Poetry** | ` ```poetry\nlines\n``` ` or auto | `<div>` per line + border/padding | Line N (every 5) |
| **Excerpt (auto)** | `>>>\ntext\n>>>` (legacy) | Auto-detect → prose/poetry | As detected |
| **Inline Code** | `` `code` `` | `<code>code</code>` | None |

**Golden Rule:** When in doubt, use explicit fences (` ```prose `, ` ```poetry `, ` ```python `) to override auto-detection and ensure predictable rendering.

---

**Maintainer:** QuizForge Core Team  
**Related Modules:** `engine/rendering/canvas/html_formatter.py`, `engine/core/questions.py`  
**For Questions:** See `dev/ARCHITECTURE.md` or `DEVELOPMENT.md`
