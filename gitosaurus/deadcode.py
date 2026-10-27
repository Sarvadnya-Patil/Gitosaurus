"""Opt-in scan for source files whose name is never mentioned anywhere else in the codebase.

This is the one analysis that needs file contents, so it downloads the repository's source files (never
media, never history) in a single request, and only after the user has seen how many files that is.
The result is a list of *candidates*: dynamic imports, entry points and config-driven loading all look
"unreferenced" to a text search, so a human has to confirm before deleting anything.
"""
from __future__ import annotations

import re

from . import insights as ins
from .git_history import _git, fetch_missing, read_blobs

MAX_SCAN_FILES = 400
CONFIG_EXTS = frozenset("json yml yaml toml cfg ini xml gradle".split())
GENERIC_STEMS = frozenset("index main app server cli __init__ __main__ setup conftest manage wsgi asgi config "
                          "settings".split())
SKIP_DIRS = frozenset("bin scripts script examples example docs doc migrations fixtures samples demo benchmarks".split())


class ScanTooLarge(RuntimeError):
    def __init__(self, count: int):
        super().__init__(f"{count} files is over the {MAX_SCAN_FILES}-file limit for a quick scan")
        self.count = count


def scan_set(files: list[str]) -> list[str]:
    """Files whose contents are needed: source plus config (config files can mention a module by name)."""
    return [p for p in files if (ins.is_source(p) or ins.ext_of(p) in CONFIG_EXTS) and not ins._ignored(p)]


def tree_oids(repo: str) -> dict[str, str]:
    out = _git(repo, "-c", "core.quotepath=false", "ls-tree", "-r", "-z", "HEAD")
    oids = {}
    for entry in filter(None, out.split("\0")):
        meta, _, path = entry.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            oids[path] = parts[2]
    return oids


def _candidate(path: str) -> bool:
    if not ins.is_source(path) or ins.is_test(path):
        return False
    parts = path.lower().split("/")
    stem = parts[-1].rsplit(".", 1)[0]
    return len(stem) >= 3 and stem not in GENERIC_STEMS and not any(p in SKIP_DIRS for p in parts[:-1]) \
        and not parts[-1].endswith(".d.ts")


def find_unreferenced(repo: str, files: list[str]) -> dict:
    scan = scan_set(files)
    if len(scan) > MAX_SCAN_FILES:
        raise ScanTooLarge(len(scan))
    oid_of = tree_oids(repo)
    fetch_missing(repo, [oid_of[p] for p in scan if p in oid_of])        # one request for the whole scan
    texts = read_blobs(repo, [oid_of[p] for p in scan if p in oid_of])
    content = {p: texts[oid_of[p]] for p in scan if oid_of.get(p) in texts}
    lowered = {p: t.lower() for p, t in content.items()}

    found = []
    for p in content:
        if not _candidate(p):
            continue
        stem = p.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        needle = stem.lower()
        word = re.compile(r"(?<![A-Za-z0-9])" + re.escape(stem) + r"(?![A-Za-z0-9])", re.I)
        referenced = any(needle in low and word.search(content[q]) for q, low in lowered.items() if q != p)
        if not referenced:
            found.append(p)
    return {"candidates": sorted(found), "scanned": len(content), "skipped": len(scan) - len(content)}
