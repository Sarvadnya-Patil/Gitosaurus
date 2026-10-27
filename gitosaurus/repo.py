"""Opening a public GitHub repository (history only, no file contents) and browsing its files."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import uuid
import urllib.request
from pathlib import Path

from .git_history import GitError, _git

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "repos"
MAX_REPO_KB = 300_000     # refuse to clone anything bigger than ~300 MB
MAX_FILE_BYTES = 300_000  # don't render huge files

# Never opened, and never downloaded: judged by extension alone, before git is asked for anything.
BLOCKED_EXTS = frozenset(
    "png jpg jpeg gif bmp webp ico icns tif tiff svg heic avif psd ai "
    "mp4 mov avi mkv webm wmv flv m4v mpg mpeg 3gp "
    "mp3 wav flac ogg aac m4a wma "
    "woff woff2 ttf otf eot "
    "zip tar gz tgz bz2 xz 7z rar jar war ear "
    "exe dll so dylib bin o a obj lib class pyc pyd wasm "
    "pdf sqlite sqlite3 db iso dmg".split()
)
BLOCKED_MESSAGE = "Images, videos and other binary files aren't opened. Pick a source or text file."


def is_viewable(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return "." not in name or name.rsplit(".", 1)[-1].lower() not in BLOCKED_EXTS

_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")

# Never let git prompt for credentials or open a login window: a private repo must just fail.
_NO_PROMPT = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
_NO_CREDS = ["-c", "credential.helper="]


class RepoError(RuntimeError):
    """A problem the user can act on; the message is safe to show."""


def _api_headers() -> dict:
    """Headers for api.github.com. An optional GITHUB_TOKEN (or GH_TOKEN) in the environment raises GitHub's
    limit from 60 to 5,000 requests an hour. It is only ever sent to api.github.com, never stored or shown."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "gitosaurus"}
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------- GitHub links

def parse_github_url(text: str) -> tuple[str, str]:
    t = text.strip()
    if t.startswith("git@") or " " in t:
        raise RepoError("Paste a link like https://github.com/owner/repo")
    t = re.sub(r"^https?://", "", t, flags=re.I)
    t = re.sub(r"^(www\.)?github\.com/", "", t, flags=re.I)
    parts = [p for p in t.split("/") if p]
    if len(parts) < 2:
        raise RepoError("Paste a link like https://github.com/owner/repo")
    owner, name = parts[0], re.sub(r"\.git$", "", parts[1])
    if not _OWNER.match(owner) or not _NAME.match(name) or name in (".", ".."):
        raise RepoError("That doesn't look like a GitHub repository link.")
    return owner, name


def check_public(owner: str, name: str) -> dict:
    """Raise RepoError unless the repo is publicly readable. Returns basic metadata."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{name}",
        headers=_api_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RepoError(
                f"**{owner}/{name}** is private or doesn't exist. Gitosaurus can only open public "
                "GitHub repositories."
            ) from e
        data = _probe_with_git(owner, name)  # rate-limited (403/429) or other API trouble
    except urllib.error.URLError as e:
        raise RepoError(f"Couldn't reach GitHub ({e.reason}). Check your connection.") from e

    size_kb = data.get("size")
    if size_kb and size_kb > MAX_REPO_KB:
        raise RepoError(f"{owner}/{name} is about {size_kb // 1024} MB, over the {MAX_REPO_KB // 1024} MB limit.")
    return {"size_kb": size_kb, "default_branch": data.get("default_branch")}


_GH_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_api_blocked_until = 0.0     # after a rate-limit answer, leave GitHub's API alone for a few minutes
API_BACKOFF_S = 300


def api_blocked() -> bool:
    """True while we are backing off because GitHub's rate limit was hit."""
    return time.time() < _api_blocked_until


def github_login_for_commit(owner: str, name: str, sha: str) -> str | None:
    """The GitHub username that authored one commit, or None (not linked to an account, a bot, rate-limited,
    offline). Exact, unlike guessing from a display name."""
    global _api_blocked_until
    if time.time() < _api_blocked_until or not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return None
    req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{name}/commits/{sha}", headers=_api_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            _api_blocked_until = time.time() + API_BACKOFF_S
        return None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
    author = data.get("author") if isinstance(data, dict) else None
    login = author.get("login") if isinstance(author, dict) else None
    return login if isinstance(login, str) and _GH_LOGIN.match(login) else None


def good_first_issues(owner: str, name: str, limit: int = 6) -> tuple[list[dict], str | None]:
    """Open beginner-friendly issues, best effort. Returns (issues, note). Issue text is untrusted data: it is
    only ever displayed (escaped by the UI), never given to the model."""
    note = None
    for label in ("good first issue", "help wanted"):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{name}/issues?state=open&per_page={limit}"
            f"&labels={urllib.parse.quote(label)}",
            headers=_api_headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            return [], ("GitHub's anonymous rate limit was reached. Try again in a while." if e.code in (403, 429)
                        else None)
        except (urllib.error.URLError, TimeoutError, ValueError):
            return [], "Couldn't reach GitHub to look for issues."
        issues = []
        for it in data if isinstance(data, list) else []:
            url = str(it.get("html_url", ""))
            if "pull_request" in it or not url.startswith("https://github.com/"):
                continue
            issues.append({"number": it.get("number"), "title": re.sub(r"\s+", " ", str(it.get("title", "")))[:90],
                           "url": url, "label": label})
        if issues:
            return issues, note
    return [], note


def _probe_with_git(owner: str, name: str) -> dict:
    proc = subprocess.run(
        ["git", *_NO_CREDS, "ls-remote", "--exit-code", f"https://github.com/{owner}/{name}.git", "HEAD"],
        capture_output=True, text=True, timeout=30, env=_NO_PROMPT,
    )
    if proc.returncode != 0:
        raise RepoError(f"**{owner}/{name}** is private or doesn't exist (or GitHub is unreachable).")
    return {}


def _partial_clone(url: str, dest: Path) -> None:
    """History only: commits and folder listings. No file contents and no working copy.

    Git then fetches individual files from the remote the moment a command needs them
    (opening a file, blame, a diff), so a repo's images, videos and old file versions are never downloaded.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Clone into a private temporary folder and move it into place only once it is complete. The real folder
    # therefore never exists half-finished, and two overlapping clones can never write into the same place.
    tmp = dest.with_name(f"{dest.name}{TMP_MARK}{os.getpid()}-{uuid.uuid4().hex[:8]}")
    try:
        proc = subprocess.run(
            ["git", *_NO_CREDS, "clone", "--quiet", "--filter=blob:none", "--no-checkout", "--single-branch",
             "--", url, str(tmp)],
            capture_output=True, text=True, timeout=900, env=_NO_PROMPT,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip().splitlines()
            raise RepoError(f"Couldn't load the repository: {err[-1] if err else 'unknown error'}")
        try:
            tmp.rename(dest)
        except OSError:
            if not _ready(dest):   # not "someone else finished first", so this is a genuine failure
                raise RepoError("Couldn't finish loading the repository. Please try again.")
    except subprocess.TimeoutExpired:
        raise RepoError("Loading the repository took too long. Please try again.") from None
    finally:
        _rmtree(tmp)   # no-op once renamed; cleans up after a failure or a lost race


TMP_MARK = ".tmp-"
_clone_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(dest: Path) -> threading.Lock:
    with _locks_guard:
        return _clone_locks.setdefault(str(dest), threading.Lock())


def _repo_url(owner: str, name: str) -> str:
    return f"https://github.com/{owner}/{name}.git"


def _ready(dest: Path) -> bool:
    """A usable clone: a .git folder whose HEAD resolves to a commit."""
    if not (dest / ".git").exists():
        return False
    proc = subprocess.run(["git", "-C", str(dest), "rev-parse", "--verify", "-q", "HEAD"],
                          capture_output=True, env=_NO_PROMPT)
    return proc.returncode == 0


def clone_repo(owner: str, name: str) -> str:
    dest = CACHE_DIR / f"{owner}__{name}"
    prune_clones(keep=str(dest))  # a different repo is being opened: nothing from earlier ones stays on disk
    with _lock_for(dest):         # overlapping page runs wait for each other instead of cloning twice
        if not _ready(dest):
            _rmtree(dest)         # a leftover from a crashed clone must not be mistaken for a good one
            _partial_clone(_repo_url(owner, name), dest)
    return str(dest)


LEASE_PREFIX = ".gitosaurus-lease."   # one file per process: ".gitosaurus-lease.<pid>"
LEASE_TTL_S = 120  # a clone used within this window belongs to a live session and is left alone


def touch_lease(path: str) -> None:
    """Mark a clone as in use by THIS process right now (every page run does this)."""
    try:
        (Path(path) / f"{LEASE_PREFIX}{os.getpid()}").touch()
    except OSError:
        pass


def _fresh_lease_pids(entry: Path) -> set[int]:
    pids = set()
    try:
        for f in entry.iterdir():
            if f.name.startswith(LEASE_PREFIX) and time.time() - f.stat().st_mtime < LEASE_TTL_S:
                pids.add(int(f.name[len(LEASE_PREFIX):]))
    except (OSError, ValueError):
        pass
    return pids


def _leased(entry: Path) -> bool:
    return bool(_fresh_lease_pids(entry))


def cleanup_on_exit() -> None:
    """Shutdown hook. Deletes cached repos, except any that ANOTHER live process used recently, so a test run
    or a second server can't pull the files out from under the process that is really using them."""
    if not CACHE_DIR.exists():
        return
    me = os.getpid()
    for entry in CACHE_DIR.iterdir():
        if entry.is_dir() and not (_fresh_lease_pids(entry) - {me}):
            remove_clone(str(entry))


def prune_clones(keep: str | None = None, respect_leases: bool = True) -> None:
    """Delete cached repos except `keep` (everything when `keep` is None).

    Clones another session used in the last LEASE_TTL_S seconds are skipped, so one tab or script can't
    delete the files under another. Deleting too early is harmless anyway: the app re-creates a missing
    clone on its next run.
    """
    if not CACHE_DIR.exists():
        return
    keep_path = Path(keep).resolve() if keep else None
    for entry in CACHE_DIR.iterdir():
        if not entry.is_dir() or entry.resolve() == keep_path:
            continue
        if TMP_MARK in entry.name and _fresh(entry):
            continue   # a clone is being downloaded into this folder right now
        if respect_leases and _leased(entry):
            continue
        remove_clone(str(entry))


def _fresh(entry: Path) -> bool:
    """Touched in the last half hour. Downloads that old are dead, so their folders are fair game."""
    try:
        return time.time() - entry.stat().st_mtime < 1800
    except OSError:
        return False


def _rmtree(p: Path) -> None:
    def _unlock(func, target, _exc):  # git marks pack files read-only, which Windows won't delete
        os.chmod(target, 0o700)
        func(target)

    if p.exists():
        shutil.rmtree(p, onerror=_unlock)


def remove_clone(path: str) -> None:
    """Delete a cached repo. Refuses anything outside the cache folder."""
    p = Path(path).resolve()
    if CACHE_DIR.resolve() in p.parents:
        _rmtree(p)


# ---------------------------------------------------------------- browsing (always at HEAD)

def list_dir(repo: str, path: str = "") -> tuple[list[str], list[str]]:
    """(folders, files) directly inside `path`, names only, folders and files each sorted."""
    out = _git(repo, "ls-tree", "-z", f"HEAD:{path}" if path else "HEAD")
    dirs, files = [], []
    for entry in filter(None, out.split("\0")):
        meta, _, name = entry.partition("\t")
        kind = meta.split()[1]
        if kind == "tree":
            dirs.append(name)
        elif kind == "blob":
            files.append(name)
    key = str.lower
    return sorted(dirs, key=key), sorted(files, key=key)


MAX_TREE_FILES = 20_000


def list_files(repo: str) -> list[str]:
    """Every file path in the repo at HEAD (for the tree), capped so the UI stays responsive."""
    out = _git(repo, "ls-tree", "-r", "-z", "--name-only", "HEAD")
    return list(filter(None, out.split("\0")))[:MAX_TREE_FILES]


def read_file(repo: str, path: str) -> str:
    if not is_viewable(path):  # checked first: must not trigger any download
        raise RepoError(BLOCKED_MESSAGE)
    size = int(_git(repo, "cat-file", "-s", f"HEAD:{path}").strip())
    if size > MAX_FILE_BYTES:
        raise RepoError(f"This file is {size // 1024} KB, too large to display (limit {MAX_FILE_BYTES // 1024} KB).")
    text = _git(repo, "show", f"HEAD:{path}")
    if "\x00" in text:
        raise RepoError("This looks like a binary file, so there are no lines to explain.")
    return text
