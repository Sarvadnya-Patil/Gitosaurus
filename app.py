import atexit
import html
import threading
from pathlib import Path

import streamlit as st

from gitosaurus import repo as rp
from gitosaurus import ui, views
from gitosaurus.git_history import GitError
from gitosaurus.highlight import TOKEN_CSS, highlight_lines
from gitosaurus.llm import LLMError, warm_up
from gitosaurus.story import MAX_SECTION_LINES, explain_range
from gitosaurus.viewer import repo_viewer

st.set_page_config(page_title="Gitosaurus", page_icon=str(Path(__file__).parent / "gitosaurus" / "assets" / "favicon.svg"),
                   layout="wide")


@st.cache_resource
def _cleanup_on_exit() -> bool:
    """Once per process: delete the cached repos when Gitosaurus shuts down (never ones another live process uses)."""
    atexit.register(rp.cleanup_on_exit)
    return True


_cleanup_on_exit()

st.html("""
<style>
  /* page: no Streamlit header, our own nav bar instead */
  header[data-testid="stHeader"], [data-testid="stToolbar"], footer { display: none; }
  .block-container { max-width: 1500px; padding: .6rem 1.5rem 1rem; }

  /* nav bar */
  /* A compact bar, one row, everything vertically centred. Left column = brand + repo chip + badge in one
     flex row (so they cannot drift apart); right column = the Change repo button at its natural size. */
  .st-key-nav { border-bottom: 1px solid rgba(128,128,128,.28); padding-bottom: .3rem; }
  .st-key-nav [data-testid="stVerticalBlock"] { gap: 0; }
  .st-key-nav [data-testid="stHorizontalBlock"] { align-items: center; gap: .75rem; flex-wrap: nowrap; }
  .st-key-nav [data-testid="stColumn"] { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
  .st-key-nav [data-testid="stColumn"]:first-child { flex: 1 1 0 !important; }
  .st-key-nav [data-testid="stMarkdownContainer"] p { margin: 0; }
  /* Streamlit gives markdown a -16px bottom margin that collapses the column and shifts our row down */
  .st-key-nav [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
  .navrow { display: flex; align-items: center; gap: .7rem; min-width: 0; }
  .brand { display: flex; align-items: center; gap: .5rem; font-size: 1.05rem; font-weight: 700; letter-spacing: -.01em;
           white-space: nowrap; line-height: 1; }
  .st-key-nav [data-testid="stHtml"] { margin: 0; }
  .repo-chip { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; line-height: 1.4;
               border: 1px solid rgba(128,128,128,.4); border-radius: 999px; padding: .05rem .65rem;
               font: 500 .76rem/1.4 ui-monospace, Consolas, monospace; }
  .st-key-nav button { min-height: 1.8rem; padding: .05rem .8rem; font-size: .8rem; white-space: nowrap; }

  /* an inline iframe reserves a few pixels of text baseline below it, which made the page scroll */
  iframe[data-testid="stCustomComponentV1"] { display: block; width: 100% !important; max-width: 100%; }

  /* connect screen */
  .st-key-connect { margin-top: 12vh; }

  /* popups: always inside the viewport with a margin; anything taller scrolls inside the popup */
  [data-testid="stDialog"] [role="dialog"] {
    width: min(920px, calc(100vw - 2rem)); max-width: 100%; box-sizing: border-box; margin-inline: auto;
    /* Streamlit already offsets the popup 3rem from the top, so 6rem leaves equal 3rem margins top and bottom */
    max-height: calc(100vh - 6rem); max-height: calc(100dvh - 6rem);
    overflow-y: auto; overflow-x: hidden;
  }
  [data-testid="stDialog"] [role="dialog"] pre, [data-testid="stDialog"] [data-testid="stCode"] { max-width: 100%; overflow-x: auto; }
  [data-testid="stDialog"] [role="dialog"] p, [data-testid="stDialog"] [role="dialog"] code { overflow-wrap: anywhere; }
</style>
""")

st.html(f"<style>{ui.CSS}</style>")

S = st.session_state
S.setdefault("repo", None)    # {"path": str, "label": "owner/name"}
S.setdefault("file", None)    # file open in the viewer
S.setdefault("nonce", None)   # last "Dig it up" request already handled
S.setdefault("view", "Onboarding")
VIEWS = list(ui.VIEW_ICONS)          # their SVG icons are attached by the stylesheet (see ui.widget_icon_css)


def go(view: str) -> None:
    S.view = view


def open_in_explorer(path: str) -> None:
    S.file, S.view = path, "Explorer"


def close_repo() -> None:
    """Runs before the page re-runs, which is the only time a widget's own state may be changed."""
    if S.repo:
        rp.remove_clone(S.repo["path"])   # nothing from this repo is left on disk
    tree_files.clear(); _file_view.clear(); views.load_all.clear()
    S.repo, S.file, S.nonce, S.view = None, None, None, "Onboarding"


@st.cache_data(show_spinner=False)
def tree_files(repo_path: str) -> list[str]:
    return rp.list_files(repo_path)


@st.cache_data(show_spinner=False, max_entries=64)
def _file_view(repo_path: str, path: str) -> dict:
    """Cached. A RepoError (binary, too large, blocked type) is a stable answer, so it is cached.
    A GitError (e.g. the local copy vanished) propagates on purpose: Streamlit never caches exceptions,
    so a temporary failure can't get stuck."""
    try:
        text = rp.read_file(repo_path, path)
    except rp.RepoError as e:
        return {"lines": [], "info": "", "error": str(e)}
    n = len(text.splitlines())
    return {"lines": highlight_lines(path, text), "info": f"{n} lines · {len(text.encode()) / 1024:.1f} KB", "error": None}


def file_view(repo_path: str, path: str) -> dict:
    """Everything the viewer needs for one file. Errors become a message, never an exception."""
    try:
        return _file_view(repo_path, path)
    except GitError as e:
        return {"lines": [], "info": "", "error": str(e)}


@st.dialog("Why does this code exist?", width="large")
def show_explanation(repo_path: str, path: str, start: int, end: int) -> None:
    span = f"line {start}" if start == end else f"lines {start}–{end}"
    st.caption(f"`{path}` · {span}")
    try:
        with st.spinner("Digging through history…"):
            r = explain_range(repo_path, path, start, end)
    except (GitError, LLMError) as e:
        st.error(str(e))
        return
    st.code(r["code"], language=None)
    st.markdown(r["answer"].replace("\n", "  \n"))
    st.divider()
    for c in r["commits"]:
        n = f" · {c.lines} line{'s' if c.lines != 1 else ''}" if len(r["commits"]) > 1 else ""
        st.markdown(f"`{c.sha[:7]}` · {c.date} · {c.author} — {c.subject}{n}")
    with st.expander("What was sent to the model (secrets redacted)"):
        for c in r["commits"]:
            st.caption(f"{c.sha[:7]} — {c.subject}")
            st.code(c.diff, language="diff")


# ------------------------------------------------------------------ nav bar

if S.repo:
    # The local copy can disappear (another tab, a restart, a cleanup). It's cheap to rebuild, so do that
    # instead of failing with "No such file or directory".
    if not (Path(S.repo["path"]) / ".git").exists():
        try:
            with st.spinner("Reloading the repository…"):
                S.repo["path"] = rp.clone_repo(*rp.parse_github_url(S.repo["label"]))
        except rp.RepoError as e:
            S.repo, S.file = None, None
            st.error(f"Couldn't reload the repository: {e}")
    if S.repo:
        rp.touch_lease(S.repo["path"])   # tells other sessions' cleanup this copy is in use

current_view = "Onboarding"
with st.container(key="nav"):
    c_main, c_views, c_action = st.columns(3, vertical_alignment="center")
    chip = f'<span class="repo-chip">{html.escape(S.repo["label"])}</span>' if S.repo else ""
    c_main.html(f'<div class="navrow"><div class="brand">{ui.logo(22)}<span>Gitosaurus</span></div>{chip}</div>')
    if S.repo:
        picked = c_views.segmented_control("View", VIEWS, key="view", label_visibility="collapsed")
        current_view = picked or S.get("_last_view", "Onboarding")   # clicking the active tab deselects it
        S["_last_view"] = current_view
        c_action.button("Change repo", on_click=close_repo)

# ------------------------------------------------------------------ connect

if S.repo is None:
    rp.prune_clones()   # nothing is open here, so clean up old visits (copies another tab is using are skipped)
    _, mid, _ = st.columns([1, 3, 1])
    with mid.container(key="connect"):
        st.html(ui.page_header("Open a public GitHub repository",
                               "Trick or treat: paste a link, pick any line of code, and find out why it haunts the repo.",
                               "pumpkin"))
        url = st.text_input("Public repository link", placeholder="https://github.com/owner/repo",
                            label_visibility="collapsed", key="gh_url")
        st.caption("Only public GitHub repositories can be opened.")
        if st.button("Open repository", type="primary", disabled=not url.strip(), key="open_repo"):
            try:
                owner, name = rp.parse_github_url(url)
                with st.spinner(f"Checking {owner}/{name}…"):
                    rp.check_public(owner, name)
                with st.spinner("Loading the history (file contents are fetched only when you open them)…"):
                    path = rp.clone_repo(owner, name)
                S.repo = {"path": path, "label": f"{owner}/{name}"}
                # Load the model in the background while the user browses, so the first question isn't a cold start.
                threading.Thread(target=warm_up, daemon=True).start()
                st.rerun()
            except rp.RepoError as e:
                st.html(ui.card("Can't open this repository", "warning", f"<p>{ui.inline(str(e))}</p>", "e"))
    st.stop()

# ------------------------------------------------------------------ screens

def explorer(repo_path: str, label: str) -> None:
    try:
        all_files = tree_files(repo_path)
    except GitError as e:
        st.error(f"Couldn't read the repository: {e}")
        return

    view = file_view(repo_path, S.file) if S.file else {"lines": [], "info": "", "error": None}
    event = repo_viewer(
        files=all_files, repo_name=label.split("/")[-1], current=S.file,
        lines=view["lines"], info=view["info"], error=view["error"],
        token_css=TOKEN_CSS, max_lines=MAX_SECTION_LINES, key="viewer",
        blocked_exts=sorted(rp.BLOCKED_EXTS), blocked_message=rp.BLOCKED_MESSAGE,
    )

    if event:
        if event["file"] != S.file:                       # user opened another file
            S.file = event["file"]
            st.rerun()
        if event.get("nonce") and event["nonce"] != S.nonce:   # user pressed "Dig it up"
            S.nonce = event["nonce"]
            show_explanation(repo_path, event["file"], event["start"], event["end"])


repo_path, label = S.repo["path"], S.repo["label"]
try:
    if current_view == "Explorer":
        explorer(repo_path, label)
    elif current_view == "Tech debt":
        views.tech_debt(repo_path, label)
    elif current_view == "Changelog":
        views.changelog(repo_path, label)
    else:
        views.onboarding(repo_path, label, open_in_explorer, go)
except GitError as e:
    st.error(f"Couldn't read the repository: {e}")
