"""Changelog and breaking-change detection between two points in history.

Commits and file lists come from history alone (no downloads). Looking for removed or changed public
declarations needs the changed files' contents, so that step fetches a few of them in one request.
Everything flagged carries its evidence, and every flag is a heuristic: a human decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import insights as ins
from .git_history import GitError, _git, fetch_missing, oids_in_raw
from .redact import redact

MAX_COMMITS = 300
MAX_DIFF_FILES = 12

CATEGORIES = ("Features", "Fixes", "Performance", "Refactoring", "Documentation", "Tests", "Build & CI", "Other")
_PREFIX = {"feat": "Features", "fix": "Fixes", "perf": "Performance", "refactor": "Refactoring", "docs": "Documentation",
           "test": "Tests", "build": "Build & CI", "ci": "Build & CI", "chore": "Other", "style": "Other",
           "revert": "Fixes"}
_KEYWORDS = (
    ("Fixes", re.compile(r"\b(fix(es|ed|ing)?|bug|hotfix|patch|resolve[sd]?|crash)\b", re.I)),
    ("Features", re.compile(r"^(add|adds|added|implement|introduce|support|allow|new|create)\b", re.I)),
    ("Performance", re.compile(r"\b(perf|performance|faster|speed up|optimi[sz]e)\b", re.I)),
    ("Documentation", re.compile(r"\b(docs?|readme|typo|comment)\b", re.I)),
    ("Tests", re.compile(r"\b(tests?|coverage)\b", re.I)),
    ("Refactoring", re.compile(r"\b(refactor|cleanup|clean up|simplify|rename)\b", re.I)),
    ("Build & CI", re.compile(r"\b(ci|build|deps?|dependenc\w+|bump|release|version)\b", re.I)),
)
BREAKING_DECLARED = re.compile(r"^\w+(\([^)]*\))?!:|BREAKING[ -]CHANGE", re.I | re.M)
BREAKING_WORDS = re.compile(
    r"\b(breaking|incompatible|no longer|drop(s|ped)? support|remov(e|es|ed|ing)|deprecat\w+|renam(e|es|ed|ing))\b", re.I)
# Housekeeping commits ("docs: remove broken link", "lint: remove unused params") can't break a user's code, so
# the keyword heuristic ignores them. An explicit "!" or "BREAKING CHANGE" is still honoured for every type.
HOUSEKEEPING = re.compile(r"^(docs?|tests?|ci|build|chore|style|lint|typo)\b\s*(\([^)]*\))?\s*[:!]", re.I)

_DECL = re.compile(
    r"^[-+]\s*(?:export\s+(?:default\s+)?|public\s+|protected\s+|pub\s+(?:\(crate\)\s+)?)?(?:async\s+)?(?:static\s+)?"
    r"(?:function\*?|class|interface|def|func|fn|type|enum|struct|const|let|var)\s+([A-Za-z_$][\w$]*)")
_EXPORT_ASSIGN = re.compile(r"^[-+]\s*(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=")
JS_EXTS = {"js", "jsx", "ts", "tsx", "mjs", "cjs"}
OO_EXTS = {"java", "kt", "cs", "scala", "rs", "php"}


@dataclass
class Release:
    name: str
    date: str


@dataclass
class RangeCommit:
    sha: str
    author: str
    subject: str
    body: str


@dataclass
class Signal:
    kind: str          # "commit" | "removed file" | "removed API" | "changed signature"
    level: str         # "declared" (the commit says so) or "possible" (our heuristic)
    detail: str
    evidence: str


def list_releases(repo: str, limit: int = 40) -> list[Release]:
    out = _git(repo, "tag", "--sort=-creatordate", "--format=%(refname:short)\x1f%(creatordate:short)")
    rels = []
    for row in out.splitlines()[:limit]:
        name, _, date = row.partition("\x1f")
        if name:
            rels.append(Release(name, date))
    return rels


def ref_exists(repo: str, ref: str) -> bool:
    try:
        _git(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
        return True
    except GitError:
        return False


def commits_between(repo: str, a: str, b: str, limit: int = MAX_COMMITS) -> tuple[list[RangeCommit], int]:
    """Commits reachable from b but not a (merges skipped): (newest `limit` of them, total count)."""
    total = int(_git(repo, "rev-list", "--count", "--no-merges", f"{a}..{b}").strip() or 0)
    out = _git(repo, "log", f"-n{limit}", "--no-merges", "--format=%H%x1f%an%x1f%s%x1f%b%x1e", f"{a}..{b}")
    commits = []
    for chunk in out.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        sha, author, subject, body = (chunk.split("\x1f") + ["", "", "", ""])[:4]
        commits.append(RangeCommit(sha, author, redact(subject), redact(body.strip())))
    return commits, total


def categorize(subject: str) -> str:
    m = ins.CONVENTIONAL_RE.match(subject)
    if m:
        return _PREFIX[m.group(1).lower()]
    for cat, rx in _KEYWORDS:
        if rx.search(subject):
            return cat
    return "Other"


def group(commits: list[RangeCommit]) -> dict[str, list[RangeCommit]]:
    out: dict[str, list[RangeCommit]] = {c: [] for c in CATEGORIES}
    for c in commits:
        out[categorize(c.subject)].append(c)
    return {k: v for k, v in out.items() if v}


def changed_files(repo: str, a: str, b: str) -> list[tuple[str, str]]:
    """(status, path) between two refs. Trees only: --no-renames keeps git from reading file contents."""
    out = _git(repo, "-c", "core.quotepath=false", "diff", "--name-status", "--no-renames", a, b)
    rows = []
    for line in out.splitlines():
        status, _, path = line.partition("\t")
        if path:
            rows.append((status[:1], path))
    return rows


def _is_public(line: str, name: str, ext: str) -> bool:
    body = line[1:]
    if ext in JS_EXTS:
        return "export" in body or bool(_EXPORT_ASSIGN.match(line))
    if ext == "py":
        return not name.startswith("_") and not body.startswith((" ", "\t"))
    if ext == "go":
        return name[:1].isupper()
    if ext in OO_EXTS:
        return bool(re.search(r"\bpub(lic)?\b", body))
    return False


def _declarations(patch: str, ext: str) -> tuple[dict[str, str], dict[str, str]]:
    removed, added = {}, {}
    for line in patch.splitlines():
        if not line or line[0] not in "+-" or line.startswith(("+++", "---")):
            continue
        m = _DECL.match(line) or _EXPORT_ASSIGN.match(line)
        if m and _is_public(line, m.group(1), ext):
            (removed if line[0] == "-" else added)[m.group(1)] = " ".join(line[1:].split())
    return removed, added


def breaking_signals(repo: str, a: str, b: str, commits: list[RangeCommit],
                     changes: list[tuple[str, str]]) -> list[Signal]:
    signals: list[Signal] = []
    for c in commits:
        text = f"{c.subject}\n{c.body}"
        if BREAKING_DECLARED.search(text):
            signals.append(Signal("commit", "declared", c.subject, c.sha[:7]))
        elif BREAKING_WORDS.search(c.subject) and not HOUSEKEEPING.match(c.subject):
            signals.append(Signal("commit", "possible", c.subject, c.sha[:7]))

    source = [(s, p) for s, p in changes if ins.is_source(p) and not ins.is_test(p)]
    for s, p in source:
        if s == "D":
            signals.append(Signal("removed file", "possible", p, "deleted between the two points"))

    # Public declarations that disappeared or changed. Needs the files' contents: fetch them in ONE request.
    inspect = [p for s, p in source if s in "MD"][:MAX_DIFF_FILES]
    if inspect:
        try:
            raw = _git(repo, "diff", "--raw", "--no-abbrev", "--no-renames", a, b, "--", *inspect)
            fetch_missing(repo, oids_in_raw(raw))
        except GitError:
            pass
        for p in inspect:
            try:
                patch = redact(_git(repo, "diff", "--unified=0", "--no-renames", a, b, "--", p))
            except GitError:
                continue
            removed, added = _declarations(patch, ins.ext_of(p))
            for name, line in removed.items():
                if name not in added:
                    signals.append(Signal("removed API", "possible", f"{name} in {p}", line[:140]))
                elif added[name] != line:
                    signals.append(Signal("changed signature", "possible", f"{name} in {p}",
                                          f"{line[:70]}  →  {added[name][:70]}"))
    order = {"declared": 0, "possible": 1}
    return sorted(signals, key=lambda s: order[s.level])
