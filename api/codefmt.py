"""Render code blocks as VSCode-style (Monokai) syntax-highlighted HTML.

Canvas New Quizzes strips <style> blocks and class-based CSS but preserves
inline `style=` attributes (verified live). So we emit inline-styled <span>s
via Pygments with noclasses=True, wrapped in our own dark <pre>.

The pusher calls highlight_html_blocks() on each item body, which finds any
<pre><code>...</code></pre> and re-renders it with real highlighting.
"""
import html
import re

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

# noclasses=True -> every span carries an inline style; nowrap=True -> no outer
# <div>/<pre> (we supply our own so we control the dark background).
_FORMATTER = HtmlFormatter(noclasses=True, style="monokai", nowrap=True)
_LEXER = PythonLexer()

_PRE_RE = re.compile(r"<pre[^>]*>\s*<code[^>]*>(.*?)</code>\s*</pre>", re.DOTALL)

_WRAPPER = (
    "<pre style='background-color:#272822;color:#F8F8F2;padding:12px;"
    "border-radius:6px;font-family:Consolas,Monaco,\"Courier New\",monospace;"
    "font-size:14px;line-height:1.5;overflow-x:auto;white-space:pre;"
    "display:block;'><code>{body}</code></pre>"
)


def render_code_block(code):
    """Plain Python source -> highlighted, inline-styled <pre> block."""
    body = highlight(code.rstrip("\n"), _LEXER, _FORMATTER).rstrip("\n")
    return _WRAPPER.format(body=body)


def highlight_html_blocks(s):
    """Replace every <pre><code>...</code></pre> in s with a highlighted version.

    Leaves all other HTML (passages, inline <code>, etc.) untouched.
    """
    def repl(m):
        return render_code_block(html.unescape(m.group(1)))

    return _PRE_RE.sub(repl, s)
