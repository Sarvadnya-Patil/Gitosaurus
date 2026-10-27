"""Scrub secrets from text before it reaches the model or the UI.

Old commits often contain credentials that were later deleted. Gitosaurus reads those
diffs, so everything it sends or displays goes through `redact` first.
"""
import re

MASK = "[REDACTED]"

_RULES = [
    # user:password@host in connection URLs (mongodb+srv://u:p@..., postgres://, https://u:p@...)
    (re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s:/@'\"]+:)[^\s@'\"]+(@)", re.I), rf"\1{MASK}\2"),
    # PEM private key blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S), MASK),
    # well-known token formats
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), MASK),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), MASK),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), MASK),  # JWT
    # name = "value" / name: 'value' where the name looks secret
    (re.compile(
        r"""((?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|auth[_-]?token|token|private[_-]?key)"""
        r"""\w*["']?\s*[:=]\s*["'])[^"'\n]{4,}(["'])""", re.I), rf"\1{MASK}\2"),
]


def redact(text: str) -> str:
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    return text
