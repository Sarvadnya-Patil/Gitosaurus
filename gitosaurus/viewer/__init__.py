"""GitHub-style repo viewer: a Streamlit custom component (plain HTML/JS, no build step).

Returns None until the user does something, then a dict:
  {"file": path}                                   - user opened a file
  {"file": path, "start": n, "end": m, "nonce": t} - user pressed "Dig it up" for lines n..m
"""
from pathlib import Path

import streamlit.components.v1 as components

_viewer = components.declare_component(
    "gitosaurus_viewer", path=str(Path(__file__).parent / "frontend")
)


def repo_viewer(*, files: list[str], repo_name: str, current: str | None, lines: list[str],
                info: str, error: str | None, token_css: str, max_lines: int,
                blocked_exts: list[str], blocked_message: str, key: str):
    """`blocked_exts` files are shown greyed out and are never requested from Python."""
    return _viewer(files=files, repo_name=repo_name, current=current, lines=lines, info=info,
                   error=error, token_css=token_css, max_lines=max_lines, blocked_exts=blocked_exts,
                   blocked_message=blocked_message, key=key, default=None)
