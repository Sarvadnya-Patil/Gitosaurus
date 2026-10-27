"""Repo-wide facts, derived only from commits and folder listings.

Nothing here reads file contents, so it runs on a partial clone without downloading a single file.
(`--no-renames` matters: git's rename detection compares file contents and would trigger downloads.)
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .git_history import _git

MAX_COMMITS = 3000
DAY = 86_400

FIX_RE = re.compile(r"\b(fix(es|ed|ing)?|bug(s|fix)?|hotfix|revert(s|ed)?|regression|crash(es)?)\b", re.I)
CONVENTIONAL_RE = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([^)]*\))?!?:", re.I)

SOURCE_EXTS = frozenset(
    "py js jsx ts tsx mjs cjs java kt scala go rs rb php cs c cc cpp h hpp swift m mm sh ps1 lua dart ex exs "
    "erl hs clj vue svelte sql".split())
IGNORED_PARTS = frozenset(
    "node_modules vendor dist build out target __pycache__ coverage third_party generated .next venv .venv "
    "bower_components".split())
LOCKFILES = frozenset("package-lock.json yarn.lock pnpm-lock.yaml cargo.lock poetry.lock go.sum composer.lock".split())
TEST_PARTS = frozenset("test tests __tests__ spec specs e2e".split())
TEST_NAME = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.|_spec\.)", re.I)
ENTRY_NAME = re.compile(r"^(main|index|app|server|cli|__main__|manage|wsgi|asgi)\.[a-z]+$", re.I)
CI_FILES = (".github/workflows/", ".gitlab-ci.yml", ".travis.yml", "jenkinsfile", ".circleci/")
DOC_NAMES = frozenset("readme.md readme readme.rst readme.txt contributing.md contributing.rst code_of_conduct.md "
                      "security.md architecture.md changelog.md history.md".split())
MANIFESTS = ("package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
             "composer.json", "Gemfile", "requirements.txt")


# ---------------------------------------------------------------- path classification

def ext_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name.lstrip(".") else ""


def _ignored(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    return (any(p in IGNORED_PARTS for p in parts[:-1]) or name.lower() in LOCKFILES
            or ".min." in name or name.endswith(".map"))


def is_source(path: str) -> bool:
    return ext_of(path) in SOURCE_EXTS and not _ignored(path)


def is_test(path: str) -> bool:
    parts = path.lower().split("/")
    return any(p in TEST_PARTS for p in parts[:-1]) or bool(TEST_NAME.search(parts[-1]))


def top_dir(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


# ---------------------------------------------------------------- history

@dataclass
class HistCommit:
    sha: str
    author: str
    ts: int
    subject: str
    files: list[str] = field(default_factory=list)
    email: str = ""


@dataclass
class FileStats:
    path: str
    commits: int = 0
    recent: int = 0            # commits in the 12 months before the newest commit
    fixes: int = 0
    authors: Counter = field(default_factory=Counter)
    first_ts: int = 0
    last_ts: int = 0

    @property
    def fix_ratio(self) -> float:
        return self.fixes / self.commits if self.commits else 0.0

    @property
    def top_author(self) -> str:
        return self.authors.most_common(1)[0][0] if self.authors else ""

    @property
    def top_share(self) -> float:
        return self.authors.most_common(1)[0][1] / self.commits if self.authors and self.commits else 0.0

    @property
    def score(self) -> float:
        return self.recent * (1 + self.fix_ratio)


_NOREPLY = re.compile(r"^(?:\d+\+)?(.+)@users\.noreply\.github\.com$", re.I)


def _name_key(name: str) -> str:
    return "n:" + re.sub(r"[^a-z0-9]", "", name.lower())


def _email_key(email: str) -> str:
    e = email.strip().lower()
    m = _NOREPLY.match(e)
    return f"g:{m.group(1)}" if m else f"e:{e}"


def resolve_identities(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Map every (name, email) seen in the history to ONE display name per person.

    git has no notion of a person, only of whatever name and email each commit was made with, so one human
    shows up as several authors ("Jane-Doe", "Jane Doe", a noreply address...). Two identities
    are the same person when they share an email or a name that matches after ignoring case, spaces and
    punctuation. The most-used spelling is the one displayed.
    """
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for name, email in pairs:
        nk = _name_key(name)
        find(nk)
        if email.strip():
            parent[find(_email_key(email))] = find(nk)       # an email and a name seen together are one person
    spellings: dict[str, Counter] = {}
    for name, _ in pairs:
        spellings.setdefault(find(_name_key(name)), Counter())[name] += 1
    best = {root: c.most_common(1)[0][0] for root, c in spellings.items()}
    return {(name, email): best[find(_name_key(name))] for name, email in pairs}


def load_history(repo: str, limit: int = MAX_COMMITS) -> list[HistCommit]:
    """Newest-first commits (merges skipped) with the files each touched. Authors are merged into people."""
    out = _git(repo, "-c", "core.quotepath=false", "log", f"-n{limit}", "--no-merges", "--no-renames",
               "--name-only", "--format=%x1e%H%x1f%an%x1f%at%x1f%s%x1f%ae")
    commits, raw = [], []
    for chunk in out.split("\x1e")[1:]:
        lines = chunk.split("\n")
        sha, author, ts, subject, email = (lines[0].split("\x1f") + ["", "", "", "", ""])[:5]
        commits.append(HistCommit(sha, author, int(ts or 0), subject, [ln for ln in lines[1:] if ln.strip()]))
        raw.append((author, email))
    who = resolve_identities(raw)       # every commit counts, so the most-used spelling really is the most used
    for c, key in zip(commits, raw):
        c.author = who[key]
        c.email = key[1]
    return commits


_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def github_login_from_email(email: str) -> str | None:
    """A GitHub username, when the commit email is one of GitHub's own 'noreply' addresses (id+user@users...).
    That is the only case where git history alone names the account."""
    m = _NOREPLY.match(email.strip())
    login = m.group(1) if m else None
    return login if login and _LOGIN.match(login) else None


def person_refs(a: "Analysis", names: set[str] | None = None, per_person: int = 2) -> dict[str, list[tuple[str, str]]]:
    """For each person: up to `per_person` (email, newest commit sha) pairs, newest first. Enough to ask
    GitHub who authored one of their commits."""
    refs: dict[str, list[tuple[str, str]]] = {}
    for c in a.commits:                                   # newest first
        if (names is not None and c.author not in names) or is_bot(c.author) or not c.email:
            continue
        mine = refs.setdefault(c.author, [])
        if len(mine) < per_person and all(e != c.email for e, _ in mine):
            mine.append((c.email, c.sha))
    return refs


TOTALS_CAP = 200_000


@dataclass
class Totals:
    commits: int
    contributors: int
    complete: bool          # False when history is longer than TOTALS_CAP: the contributor count is then a lower bound
                            # (the commit count is always exact)


def history_totals(repo: str, cap: int = TOTALS_CAP) -> Totals:
    """Whole-history commit and contributor counts. Only commit headers are read, never file lists, so this
    stays cheap even when the detailed analysis only looks at the most recent commits. Bots aren't people."""
    out = _git(repo, "log", "--no-merges", f"-n{cap}", "--format=%an%x1f%ae")
    pairs = []
    for line in out.splitlines():
        name, _, email = line.partition("\x1f")
        pairs.append((name, email))
    who = resolve_identities(pairs)
    # GitHub's "N commits" counts merge commits too, so use the same definition to be comparable with it.
    every = int(_git(repo, "rev-list", "--count", "HEAD").strip() or 0)
    return Totals(every, len({n for n in who.values() if not is_bot(n)}), len(pairs) < cap)


@dataclass
class Analysis:
    commits: list[HistCommit]
    stats: dict[str, FileStats]
    files: list[str]
    ref_ts: int                 # timestamp of the newest commit: "now", as far as this repo is concerned
    complete: bool              # False when the repo has more history than we looked at


def analyze(commits: list[HistCommit], files: list[str], limit: int = MAX_COMMITS) -> Analysis:
    """`limit` must be the same limit `load_history` was given: it is how we tell whether history was cut short."""
    present = set(files)
    ref = commits[0].ts if commits else 0
    stats: dict[str, FileStats] = {}
    for c in commits:
        fix = bool(FIX_RE.search(c.subject))
        recent = ref - c.ts <= 365 * DAY
        for f in c.files:
            if f not in present:
                continue
            s = stats.setdefault(f, FileStats(f))
            s.commits += 1
            s.fixes += fix
            s.recent += recent
            s.authors[c.author] += 1
            s.last_ts = s.last_ts or c.ts           # newest first, so the first sighting is the latest change
            s.first_ts = c.ts
    return Analysis(commits, stats, files, ref, complete=len(commits) < limit)


# ---------------------------------------------------------------- tech debt

def hotspots(a: Analysis, n: int = 15) -> list[FileStats]:
    """Source files that change a lot, and where many of the changes are fixes."""
    pool = [s for p, s in a.stats.items() if is_source(p) and not is_test(p) and s.commits >= 2 and s.recent > 0]
    return sorted(pool, key=lambda s: (-s.score, -s.commits))[:n]


def knowledge_risk(a: Analysis, n: int = 10) -> list[FileStats]:
    """Files that are changed often but almost always by one person."""
    if len({c.author for c in a.commits}) < 2:
        return []   # a one-person project: every file would be flagged, which says nothing
    pool = [s for p, s in a.stats.items() if is_source(p) and not is_test(p) and s.commits >= 5 and s.top_share >= 0.8]
    return sorted(pool, key=lambda s: -s.commits)[:n]


@dataclass
class FolderStat:
    path: str
    depth: int          # 1 = top-level folder, 2 = a folder directly inside one
    files: int          # files in it now (any type)
    changes: int        # commits touching it in the last 12 months (any file type)
    fixes: int          # ...of which look like fixes
    risk: float         # summed hotspot score of its source files; 0 when it holds no code


def _folder_keys(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    return ["/".join(parts[:d]) for d in (1, 2) if len(parts) >= d]


def folder_map(a: Analysis) -> list[FolderStat]:
    """EVERY folder (two levels deep), not only the ones with code, each followed by its sub-folders.

    Risk only exists for source files, so a docs or config folder shows 0 risk but still shows how much it
    changes and how big it is.
    """
    files: Counter = Counter()
    for p in a.files:
        files.update(_folder_keys(p))
    changes: Counter = Counter()
    fixes: Counter = Counter()
    for c in a.commits:
        if a.ref_ts - c.ts > 365 * DAY:
            continue
        touched = {k for f in c.files for k in _folder_keys(f) if k in files}
        changes.update(touched)
        if FIX_RE.search(c.subject):
            fixes.update(touched)
    risk: Counter = Counter()
    for p, s in a.stats.items():
        if is_source(p) and not is_test(p):
            for k in _folder_keys(p):
                risk[k] += s.score
    stats = {k: FolderStat(k, k.count("/") + 1, n, changes[k], fixes[k], round(risk[k], 1)) for k, n in files.items()}

    def order(items):
        return sorted(items, key=lambda f: (-f.risk, -f.changes, f.path.lower()))

    out: list[FolderStat] = []
    for top in order(f for f in stats.values() if f.depth == 1):
        out.append(top)
        out.extend(order(f for f in stats.values() if f.depth == 2 and f.path.startswith(top.path + "/")))
    return out


@dataclass
class Dormant:
    path: str
    last_ts: int | None         # None: not changed anywhere in the history we looked at


def dormant_files(a: Analysis, months: int = 18, n: int = 40) -> list[Dormant]:
    """Source files nobody has touched for a long time, while the project itself kept moving."""
    cutoff = a.ref_ts - months * 30 * DAY
    out = []
    for p in a.files:
        if not is_source(p) or is_test(p):
            continue
        s = a.stats.get(p)
        if s is None:
            if a.commits:
                out.append(Dormant(p, None))
        elif s.last_ts < cutoff:
            out.append(Dormant(p, s.last_ts))
    out.sort(key=lambda d: d.last_ts or 0)
    return out[:n]


# ---------------------------------------------------------------- people, structure, conventions

def monthly_activity(a: Analysis, months: int = 24) -> list[int]:
    """Commits per ~30-day month, oldest first, ending at the newest commit."""
    counts = [0] * months
    for c in a.commits:
        age = (a.ref_ts - c.ts) // (30 * DAY)
        if 0 <= age < months:
            counts[months - 1 - age] += 1
    return counts


def is_bot(name: str) -> bool:
    low = name.lower()
    return low.endswith("[bot]") or low in {"dependabot", "github-actions", "renovate", "greenkeeper"}


def people(a: Analysis) -> dict:
    """Who to ask. Bots are left out: they are not people."""
    overall = Counter(c.author for c in a.commits if not is_bot(c.author))
    recent90 = Counter(c.author for c in a.commits if a.ref_ts - c.ts <= 90 * DAY and not is_bot(c.author))
    dirs = Counter(top_dir(p) for p in a.files)
    owners: dict[str, list[tuple[str, int]]] = {}
    for d, n_files in dirs.items():
        if n_files < 3:
            continue
        c = Counter()
        for commit in a.commits:
            if a.ref_ts - commit.ts > 365 * DAY:
                continue
            if not is_bot(commit.author) and any(top_dir(f) == d for f in commit.files):
                c[commit.author] += 1
        if c:
            owners[d] = c.most_common(2)
    # "in_window": only the commits we analysed in detail. For all-time numbers use history_totals().
    return {"overall": overall.most_common(6), "recent90": recent90.most_common(5), "owners": owners,
            "contributors_in_window": len(overall)}


def structure(files: list[str]) -> dict:
    top = Counter(top_dir(p) for p in files)
    langs = Counter(ext_of(p) for p in files if is_source(p))
    entry = sorted((p for p in files if ENTRY_NAME.match(p.rsplit("/", 1)[-1]) and p.count("/") <= 2 and not is_test(p)
                    and not _ignored(p)), key=lambda p: (p.count("/"), p))[:8]
    test_dirs = sorted({"/".join(p.split("/")[:i + 1]) for p in files for i, part in enumerate(p.split("/")[:-1])
                        if part.lower() in TEST_PARTS})[:6]
    ci = any(p.lower().startswith(CI_FILES) for p in files)
    docs = [p for p in files if p.rsplit("/", 1)[-1].lower() in DOC_NAMES and p.count("/") <= 1][:8]
    return {"top": top.most_common(12), "langs": langs.most_common(6), "entry": entry, "tests": test_dirs,
            "ci": ci, "docs": docs, "total": len(files)}


def conventions(a: Analysis) -> dict:
    n = len(a.commits)
    conv = sum(1 for c in a.commits if CONVENTIONAL_RE.match(c.subject))
    return {"conventional_pct": round(100 * conv / n) if n else 0, "commits": n}


def key_docs(repo: str, files: list[str]) -> dict[str, str]:
    """README, CONTRIBUTING and the project manifest, truncated. Fetches at most three small files."""
    from .repo import RepoError, read_file       # local import: repo.py imports git_history, not the other way round
    from .git_history import GitError
    root = {p.lower(): p for p in files if "/" not in p}
    picks = []
    for want, cap in (("readme", 3500), ("contributing", 1800)):
        hit = next((orig for low, orig in sorted(root.items()) if low.startswith(want)), None)
        if hit:
            picks.append((hit, cap))
    manifest = next((m for m in MANIFESTS if m in root.values()), None)
    if manifest:
        picks.append((manifest, 1200))
    out = {}
    for path, cap in picks:
        try:
            out[path] = read_file(repo, path)[:cap]
        except (RepoError, GitError):
            continue
    return out


def describe_when(ts: int | None, ref: int) -> str:
    if ts is None:
        return "not in the history window"
    days = max(0, (ref - ts) // DAY)
    if days < 60:
        return f"{days} days before the latest commit"
    if days < 700:
        return f"{round(days / 30)} months before the latest commit"
    return f"{days / 365:.1f} years before the latest commit"
