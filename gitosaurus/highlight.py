"""Syntax highlighting: one balanced HTML string per source line."""
from html import escape

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.util import ClassNotFound

# The viewer scopes these under `.dark .hl` / `.light .hl` and switches with the Streamlit theme.
TOKEN_CSS = (
    HtmlFormatter(style="github-dark").get_style_defs(".dark .hl")
    + HtmlFormatter(style="default").get_style_defs(".light .hl")
)


def highlight_lines(path: str, text: str) -> list[str]:
    lines = text.splitlines()
    try:
        try:
            lexer = get_lexer_for_filename(path, text, stripnl=False)
        except ClassNotFound:
            lexer = TextLexer(stripnl=False)
        out = highlight(text, lexer, HtmlFormatter(nowrap=True)).split("\n")
    except Exception:  # a lexer blowing up must never break browsing
        return [escape(ln) for ln in lines]
    out = out[:len(lines)]
    out += [""] * (len(lines) - len(out))
    return out
