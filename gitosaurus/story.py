"""Turn git history into a cited 'story' using Gemma."""
from . import git_history as gh
from .llm import ask, DEFAULT_MODEL
from .redact import redact

MAX_SECTION_LINES = 80
MAX_ORIGIN_COMMITS = 3  # distinct commits whose diffs are sent in full
ORIGIN_DIFF_CHARS = 4000

SYSTEM = (
    "You are Gitosaurus, a code archaeologist. Explain why code exists using ONLY the git "
    "history provided. Cite commits by their short hash like [a1b2c3d]. Never guess a reason "
    "that the history does not state. Values shown as [REDACTED] are secrets that were removed; "
    "never try to reconstruct them. Reply in exactly this format, at most 5 short lines:\n"
    "What changed: <what the commit(s) did to the selected code, from the diff>\n"
    "Stated reason: <quote or closely paraphrase the commit message/body/issue refs, or write "
    "'None recorded' if the messages do not give a reason (e.g. 'initial commit', 'fix', 'update')>\n"
    "Likely intent: <one inference, clearly labelled as inference, or 'Unknown'>\n"
    "Sources: <commit hashes>"
)


def _format(c: gh.Commit, with_diff: bool = True) -> str:
    refs = f"\nReferences: {', '.join(c.refs)}" if c.refs else ""
    head = f"Commit {c.sha[:7]} by {c.author} on {c.date}\nSubject: {c.subject}\n{c.body}{refs}"
    return f"{head}\nDiff:\n{c.diff}" if with_diff else head


def explain_range(repo: str, path: str, start: int, end: int, model: str = DEFAULT_MODEL,
                  think: bool = False) -> dict:
    """Explain lines start..end (inclusive, 1-based) of `path`."""
    if end < start:
        start, end = end, start
    if end - start + 1 > MAX_SECTION_LINES:
        raise gh.GitError(f"Select at most {MAX_SECTION_LINES} lines at a time.")
    lines = gh.read_lines(repo, path)
    if not 1 <= start <= end <= len(lines):
        raise gh.GitError(f"Lines {start}-{end} are outside the file ({len(lines)} lines).")
    code = redact("\n".join(lines[start - 1:end]))

    gh.prefetch_file_history(repo, path)  # one batched download instead of one round trip per old version
    blamed = gh.blame_range(repo, path, start, end)
    origins = []
    for sha, count in blamed[:MAX_ORIGIN_COMMITS]:
        c = gh.commit_details(repo, sha, path, max_diff=ORIGIN_DIFF_CHARS)
        c.lines = count
        origins.append(c)
    seen = {c.sha for c in origins}
    # Background only: messages without diffs, to keep the prompt inside the context window.
    recent = [c for c in gh.file_history(repo, path, limit=6, max_diff=0) if c.sha not in seen][:4]

    where = f"line {start}" if start == end else f"lines {start}-{end}"
    prompt = (
        f"File: {path}\nSelected {where}:\n{code}\n\n"
        f"=== Commit(s) that last changed the selected code ===\n"
        + "\n\n".join(f"({c.lines} of the selected lines)\n{_format(c)}" for c in origins)
        + "\n\n=== Other recent commits to this file (messages only) ===\n"
        + "\n\n".join(_format(c, with_diff=False) for c in recent)
        + "\n\nQuestion: Why does the selected code exist? Follow the required format."
    )
    return {
        "answer": ask(prompt, model=model, system=SYSTEM, think=think),
        "commits": origins, "recent": recent, "code": code, "start": start, "end": end,
    }


def explain_line(repo: str, path: str, line: int, model: str = DEFAULT_MODEL, think: bool = False) -> dict:
    return explain_range(repo, path, line, line, model, think)
