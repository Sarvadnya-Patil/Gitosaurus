"""Pull the history of a line, a section or a file out of git. No LLM involved here.

Everything reads at HEAD so that what the user sees in the file browser is exactly what is blamed.
"""
import os
import re
import subprocess
from dataclasses import dataclass, field

from .redact import redact

MAX_DIFF_CHARS = 6000
_BLAME_HEADER = re.compile(r"^([0-9a-f]{40}) \d+ \d+")


class GitError(RuntimeError):
    pass


# Partial clones fetch missing files from the remote on demand; never let that prompt for a login.
_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


def _git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "credential.helper=", "-C", repo, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=_ENV,
    )
    if proc.returncode != 0:
        raise GitError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


@dataclass
class Commit:
    sha: str
    author: str
    date: str
    subject: str
    body: str = ""
    diff: str = ""
    refs: list[str] = field(default_factory=list)  # issue/PR numbers like #123
    lines: int = 0  # how many of the selected lines this commit last touched


def prefetch_file_history(repo: str, path: str, limit: int = 40) -> None:
    """Download the recent versions of one file in a single request.

    In a partial clone git otherwise fetches each old version separately while blaming (~1 s each).
    Only this file's last `limit` versions are fetched, never the rest of the repository.
    Best effort: any failure just means git fetches lazily later.
    """
    try:
        raw = _git(repo, "log", "--follow", f"-n{limit}", "--format=", "--raw", "--no-abbrev", "--", path)
        fetch_missing(repo, oids_in_raw(raw))
    except (GitError, subprocess.SubprocessError, OSError):
        pass


def oids_in_raw(raw: str) -> set[str]:
    """Object ids mentioned in `git ... --raw --no-abbrev` output (the all-zero 'no file' id is skipped)."""
    return {o for row in raw.splitlines() if row.startswith(":") for o in row.split()[2:4] if set(o) != {"0"}}


def fetch_missing(repo: str, oids, timeout: int = 180) -> int:
    """Download whichever of `oids` this partial clone doesn't have yet, in ONE request. Returns how many
    were missing. Best effort: failures just mean git fetches lazily later."""
    oids = sorted(set(oids))
    if not oids:
        return 0
    try:
        # Bytes, not text: Windows text mode would turn "\n" into "\r\n" and corrupt the object ids.
        check = subprocess.run(
            ["git", "--no-lazy-fetch", "-C", repo, "cat-file", "--batch-check"],
            input=("\n".join(oids) + "\n").encode(), capture_output=True, env=_ENV,
        )
        missing = [row.split()[0] for row in check.stdout.decode().splitlines() if row.endswith(" missing")]
        if missing:
            subprocess.run(
                ["git", "-c", "credential.helper=", "-c", "fetch.negotiationAlgorithm=noop", "-C", repo,
                 "fetch", "origin", "--no-tags", "--no-write-fetch-head", "--recurse-submodules=no",
                 "--filter=blob:none", "--stdin"],
                input=("\n".join(missing) + "\n").encode(), capture_output=True, env=_ENV, timeout=timeout,
            )
        return len(missing)
    except (subprocess.SubprocessError, OSError):
        return 0


def read_blobs(repo: str, oids, max_bytes: int = 200_000) -> dict[str, str]:
    """oid -> text for blobs that are present locally and not larger than `max_bytes`. Fetches nothing."""
    oids = sorted(set(oids))
    if not oids:
        return {}
    feed = ("\n".join(oids) + "\n").encode()
    sizes = subprocess.run(["git", "--no-lazy-fetch", "-C", repo, "cat-file", "--batch-check"],
                           input=feed, capture_output=True, env=_ENV).stdout.decode().splitlines()
    wanted = [r.split()[0] for r in sizes if len(r.split()) == 3 and int(r.split()[2]) <= max_bytes]
    if not wanted:
        return {}
    data = subprocess.run(["git", "--no-lazy-fetch", "-C", repo, "cat-file", "--batch"],
                          input=("\n".join(wanted) + "\n").encode(), capture_output=True, env=_ENV).stdout
    out, pos = {}, 0
    while pos < len(data):
        nl = data.index(b"\n", pos)
        head = data[pos:nl].decode().split()
        if len(head) == 3:
            size = int(head[2])
            body = data[nl + 1: nl + 1 + size]
            if b"\x00" not in body:
                out[head[0]] = body.decode("utf-8", errors="replace")
            pos = nl + 1 + size + 1
        else:                       # "<oid> missing"
            pos = nl + 1
    return out


def head_sha(repo: str) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


def read_lines(repo: str, path: str) -> list[str]:
    return _git(repo, "show", f"HEAD:{path}").splitlines()


def blame_range(repo: str, path: str, start: int, end: int) -> list[tuple[str, int]]:
    """Commits that last touched lines start..end, as (sha, line_count), most lines first."""
    out = _git(repo, "blame", "HEAD", "-L", f"{start},{end}", "--porcelain", "--", path)
    counts: dict[str, int] = {}
    sha = None
    for row in out.splitlines():
        m = _BLAME_HEADER.match(row)
        if m:
            sha = m.group(1)
        elif row.startswith("\t") and sha:
            counts[sha] = counts.get(sha, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


def blame_line(repo: str, path: str, line: int) -> str:
    """Return the full sha of the commit that last touched `path:line`."""
    return blame_range(repo, path, line, line)[0][0]


def commit_details(repo: str, sha: str, path: str | None = None, max_diff: int = MAX_DIFF_CHARS) -> Commit:
    """Metadata plus the diff (limited to `path` if given, truncated). Secrets are redacted."""
    sep = "\x1f"
    meta = _git(repo, "show", "-s", f"--format=%H{sep}%an{sep}%ad{sep}%s{sep}%b", "--date=short", sha)
    sha_, author, date, subject, body = (meta.split(sep, 4) + [""] * 5)[:5]
    diff_args = ["show", "--format=", "--unified=3", sha]
    if path:
        diff_args += ["--", path]
    # redact before truncating so a secret can't be cut in half and slip through
    diff = redact(_git(repo, *diff_args))
    if len(diff) > max_diff:
        diff = diff[:max_diff] + "\n... [diff truncated]"
    refs = sorted(set(re.findall(r"#\d+", f"{subject}\n{body}")))
    return Commit(sha_.strip(), author, date, redact(subject), redact(body.strip()), diff, refs)


def file_history(repo: str, path: str, limit: int = 15, max_diff: int = MAX_DIFF_CHARS) -> list[Commit]:
    """Most recent commits touching a file (follows renames)."""
    out = _git(repo, "log", "--follow", f"-n{limit}", "--format=%H", "--", path)
    return [commit_details(repo, s, path, max_diff) for s in out.split()]


def read_line(repo: str, path: str, line: int) -> str:
    lines = read_lines(repo, path)
    if not 1 <= line <= len(lines):
        raise GitError(f"line {line} out of range (file has {len(lines)} lines)")
    return redact(lines[line - 1])
