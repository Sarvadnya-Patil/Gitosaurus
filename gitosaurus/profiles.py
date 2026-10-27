"""Link the people shown in the app to their GitHub profiles.

git history holds names and emails, never GitHub usernames, so a username is only claimed when it is certain:
  1. the commit email is GitHub's own noreply address (`123+user@users.noreply.github.com`), or
  2. GitHub itself says that user authored one of the person's commits.
Anyone we can't resolve stays unlinked. We never guess from a display name: two different people can share one.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from . import insights as ins
from . import repo as rp


def _login(owner: str, name: str, candidates: list[tuple[str, str]]) -> str | None:
    for email, _ in candidates:                              # free and exact
        login = ins.github_login_from_email(email)
        if login:
            return login
    for _, sha in candidates[:2]:                            # one request per candidate, at most two
        login = rp.github_login_for_commit(owner, name, sha)
        if login:
            return login
    return None


def resolve(owner: str, name: str, refs: dict[str, list[tuple[str, str]]]) -> dict[str, str | None]:
    """person -> GitHub username, or None when it can't be known for certain."""
    if not refs:
        return {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {person: pool.submit(_login, owner, name, cands) for person, cands in refs.items()}
        return {person: f.result() for person, f in futures.items()}
