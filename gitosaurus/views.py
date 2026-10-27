"""The Onboarding, Tech debt and Changelog screens (Streamlit rendering only; the logic lives elsewhere).

Fast, git-derived facts are drawn first. The Gemma-written parts are drawn into placeholders afterwards,
so the page is useful immediately and the model never blocks it.
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd
import streamlit as st

from . import changelog as cl
from . import deadcode as dc
from . import guides
from . import insights as ins
from . import profiles
from . import repo as rp
from . import ui
from .git_history import GitError, _git, head_sha
from .llm import LLMError, ask

S = st.session_state

def md(text: str) -> str:
    """Escape markdown so commit messages and issue titles can't change the page's formatting."""
    return re.sub(r"([\\`*_{}\[\]<>#|~])", r"\\\1", str(text))


def _date(ts: int | None) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d") if ts else "-"


# ---------------------------------------------------------------- cached work

@st.cache_data(show_spinner=False, max_entries=6)
def load_all(repo_path: str, head: str):
    """(analysis of recent commits, files, key docs, whole-history totals). `head` is part of the cache key so a
    changed repo is re-read."""
    files = rp.list_files(repo_path)
    return (ins.analyze(ins.load_history(repo_path), files), files, ins.key_docs(repo_path, files),
            ins.history_totals(repo_path))


@st.cache_data(show_spinner=False, max_entries=16)
def _llm(system: str, prompt: str) -> str:
    return ask(prompt, system=system)        # an LLMError is never cached, so a hiccup can't stick


@st.cache_data(show_spinner=False, ttl=600, max_entries=8)
def _issues(owner: str, name: str):
    return rp.good_first_issues(owner, name)


@st.cache_data(show_spinner=False, ttl=900, max_entries=16)
def _logins(owner: str, name: str, refs: dict):
    """(person -> verified GitHub username or None, whether GitHub's rate limit stopped us). Short-lived, so a
    rate-limited miss isn't remembered for long."""
    logins = profiles.resolve(owner, name, refs)
    return logins, rp.api_blocked()


CONTRIBUTOR_NOTE = ("Commits include merges, like GitHub's count. Contributors are the distinct people in the git history "
                    "(names and emails merged, bots left out); GitHub counts accounts, which git doesn't record, "
                    "so its number can differ a little.")


@st.cache_data(show_spinner=False, max_entries=8)
def _compare(repo_path: str, head: str, a: str, b: str) -> dict:
    commits, total = cl.commits_between(repo_path, a, b)
    changes = cl.changed_files(repo_path, a, b)
    return {"commits": commits, "total": total, "changes": changes, "groups": cl.group(commits),
            "signals": cl.breaking_signals(repo_path, a, b, commits, changes)}


def narrate(slot, system: str, prompt: str, wait: str, wide: bool = False) -> str | None:
    """Fill `slot` with a Gemma answer drawn as cards. While the model works, a skeleton shows; a failure shows
    a message and the facts around it stay visible."""
    slot.html(ui.guide_skeleton(wait))
    try:
        text = _llm(system, prompt)
    except LLMError as e:
        slot.html(ui.card("Gemma couldn't write this part", "warning", f"<p>{ui.esc(str(e))}</p>", "e"))
        return None
    slot.html(ui.guide_cards(text, wide=wide))
    return text


# ---------------------------------------------------------------- onboarding

def onboarding(repo_path: str, label: str, open_file, go) -> None:
    owner, name = rp.parse_github_url(label)
    a, files, docs, totals = load_all(repo_path, head_sha(repo_path))
    if not a.commits:
        st.html(ui.page_header(name, "No commits to learn from yet.", "info"))
        return
    s, p = ins.structure(files), ins.people(a)

    st.html(ui.hero(name, label, [
        ("commit", f"{totals.commits:,}", "commits"),
        ("users", f"~{totals.contributors:,}{'' if totals.complete else '+'}", "contributors (est.)"),
        ("file", f"{s['total']:,}", "files"),
        ("calendar", _date(a.ref_ts), "latest commit")], ins.monthly_activity(a), note=CONTRIBUTOR_NOTE))
    st.html('<div class="g-gap"></div>')

    left, right = st.columns([3, 2], gap="large")
    with left:
        guide_slot = st.empty()
    with right:
        starts = [x for x in dict.fromkeys(s["docs"][:3] + s["entry"][:4]) if rp.is_viewable(x)]
        with st.container(key="startbox"):
            st.html(f'<h4 class="g-boxhead"><span class="g-ico t-b">{ui.icon("flag", 17)}</span>Start here</h4>')
            with st.container(key="start"):
                for i, path in enumerate(starts):
                    st.button(path, key=f"start::{i}", on_click=open_file, args=(path,), width="stretch")
            st.html(f'<p class="g-muted g-tight">{"Opens the file in the Explorer." if starts else "No README or obvious entry point found."}</p>')
        st.html('<div class="g-gap sm"></div>')
        who_slot = st.empty()
        issues, note = _issues(owner, name)
        st.html(ui.card("Good first issues (the treats)", "pumpkin", ui.issues_list(issues, note), "a"))

    st.html(ui.section_title("Tread carefully: here be ghosts", "skull"))
    hot, risky = ins.hotspots(a, 5), ins.knowledge_risk(a, 5)
    c1, c2 = st.columns(2, gap="large")
    c1.html(ui.card("Haunted: changes the most, often to fix something", "cauldron", ui.hotspot_rows(hot), "c"))
    owner_slot = c2.empty()
    st.button("Open the full tech-debt map", key="debt_link", on_click=go, args=("Tech debt",))

    overall = dict(p["overall"])

    def draw_people(logins=None, limited=False):
        foot = "Who changed each folder most in the last year."
        if logins and any(logins.values()):
            foot += " Click a name to open their GitHub profile."
        if limited and logins and not all(logins.values()):
            foot += (" Some names aren't linked yet because GitHub's anonymous rate limit was reached; "
                     "set a GITHUB_TOKEN to raise it.")
        who_slot.html(ui.card("Who to ask (the spirits who know)", "ghost", ui.people_list(p["owners"], overall, logins) +
                              f'<p class="g-muted g-tight">{ui.esc(foot)}</p>', "d"))
        owner_slot.html(ui.card("Lone souls: almost always changed by one person", "skull", ui.owner_rows(risky, logins), "e"))

    draw_people()                                         # plain pills first: nothing waits on the network
    shown = {n for who in p["owners"].values() for n, _ in who} | {r.top_author for r in risky}
    logins, limited = _logins(owner, name, ins.person_refs(a, shown))
    if any(logins.values()) or limited:
        draw_people(logins, limited)                      # verified names become links; a limit is explained

    narrate(guide_slot, guides.ONBOARDING_SYSTEM, guides.onboarding_prompt(label, a, files, docs, totals),
            "Gemma is brewing your guide in the cauldron…")


# ---------------------------------------------------------------- tech debt & dead code

def tech_debt(repo_path: str, label: str) -> None:
    head = head_sha(repo_path)
    a, files, _, _ = load_all(repo_path, head)
    scope = "" if a.complete else " (the most recent ones; older history isn't included)"
    st.html(ui.page_header(
        "Tech debt & dead code",
        f"Haunted houses, lone souls, a graveyard and ghost files. Based on {len(a.commits):,} commits{scope}: "
        "signals from history, not verdicts. The first three tabs download no file contents.", "ghost"))
    if not a.commits:
        st.info("No history to analyse.")
        return
    with st.container(key="debttabs"):       # the key lets the stylesheet put an SVG icon on each tab
        t1, t2, t3, t4 = st.tabs(["Haunted hotspots", "Knowledge risk", "Dormant files (graveyard)",
                                  "Unreferenced files (ghosts)"])

    with t1:
        hot = ins.hotspots(a, 15)
        if not hot:
            st.info("No source file stands out.")
        else:
            top = max(h.score for h in hot) or 1
            st.dataframe(pd.DataFrame([{
                "File": h.path, "Risk": round(h.score, 1), "Changes (12 mo)": h.recent, "Fixes": h.fixes,
                "Authors": len(h.authors), "Last change": _date(h.last_ts)} for h in hot]),
                hide_index=True, width="stretch",
                column_config={"Risk": st.column_config.ProgressColumn(min_value=0, max_value=top, format="%.1f")})
            st.caption("Risk = changes in the last year × (1 + share of those that are fixes).")
            flag = f"debt_explain::{head}"
            if st.button("Explain these with Gemma", key="explain_debt"):
                S[flag] = True
            if S.get(flag):
                narrate(st.empty(), guides.DEBT_SYSTEM, guides.debt_prompt(a, hot[:6]),
                        "Gemma is reading the tombstones…", wide=True)
        st.html('<div class="g-gap"></div>')
        st.html(ui.card("Every folder", "tombstone",
                        ui.folder_rows(ins.folder_map(a)) +
                        '<p class="g-muted g-tight">Bar = hotspot risk of the code inside (empty for folders with no code). '
                        'Changes counted over the last 12 months.</p>', "d"))

    with t2:
        risky = ins.knowledge_risk(a)
        if not risky:
            st.info("No file depends on a single person (or this is a one-person project).")
        else:
            st.dataframe(pd.DataFrame([{
                "File": r.path, "Mostly changed by": r.top_author, "Share": f"{round(r.top_share * 100)}%",
                "Commits": r.commits} for r in risky]), hide_index=True, width="stretch")
            st.caption("If that person leaves, these are the files nobody else has worked on.")

    with t3:
        dormant = ins.dormant_files(a)
        if not dormant:
            st.info("Every source file has been touched recently.")
        else:
            oldest = _date(a.commits[-1].ts)
            st.dataframe(pd.DataFrame([{
                "File": d.path, "Last changed": _date(d.last_ts) if d.last_ts else f"before {oldest}"} for d in dormant]),
                hide_index=True, width="stretch")
            st.caption("No change for 18+ months while the project kept moving. Dormant is not the same as dead: "
                       "stable code looks identical. Use the next tab to check whether anything still refers to them.")

    with t4:
        scan = dc.scan_set(files)
        st.markdown(f"Finding files that nothing mentions means reading code, so this tab **downloads {len(scan):,} "
                    "source and config files** (no images, no history), in one request, and then searches them locally.")
        if len(scan) > dc.MAX_SCAN_FILES:
            st.warning(f"That's over the {dc.MAX_SCAN_FILES}-file limit for a quick scan, so it's switched off here.")
        else:
            key = f"unref::{head}"
            if st.button(f"Download {len(scan):,} files and hunt for ghosts", key="scan_ghosts"):
                with st.spinner("Downloading and searching for ghosts…"):
                    try:
                        S[key] = dc.find_unreferenced(repo_path, files)
                    except (GitError, dc.ScanTooLarge) as e:
                        st.error(str(e))
            res = S.get(key)
            if res:
                st.caption(f"Searched {res['scanned']:,} files" + (f" ({res['skipped']} skipped: too large)" if res["skipped"] else ""))
                if res["candidates"]:
                    st.dataframe(pd.DataFrame({"Possibly unused": res["candidates"]}), hide_index=True,
                                 width="stretch")
                    st.caption("Candidates only: dynamic imports, entry points and config-driven loading look unreferenced "
                               "to a text search. Check before deleting.")
                else:
                    st.html(ui.notice("No ghosts", "Every source file is mentioned somewhere else.", "ghost", "a"))


# ---------------------------------------------------------------- changelog & breaking changes

def _markdown_export(a: str, b: str, data: dict, summary: str | None) -> str:
    out = [f"# {a} → {b}", f"{data['total']} commits, {len(data['changes'])} files changed.", ""]
    if summary:
        out += [summary, ""]
    if data["signals"]:
        out += ["## Possible breaking changes", ""]
        out += [f"- **{s.level}** · {s.kind}: {s.detail}  \n  `{s.evidence}`" for s in data["signals"]] + [""]
    for cat, commits in data["groups"].items():
        out += [f"## {cat}", ""] + [f"- {c.subject} (`{c.sha[:7]}`, {c.author})" for c in commits] + [""]
    return "\n".join(out)


def changelog(repo_path: str, label: str) -> None:
    head = head_sha(repo_path)
    st.html(ui.page_header("Changelog & breaking changes",
                           "Your spellbook: compare two releases, or the latest commits, and spot the curses "
                           "(breaking changes) before they bite users.", "scroll"))
    try:
        rels = cl.list_releases(repo_path)
        n_commits = int(_git(repo_path, "rev-list", "--count", "--no-merges", "HEAD").strip() or 0)
    except GitError as e:
        st.html(ui.notice("Couldn't read this repository's history", str(e), "warning", "e"))
        return
    if n_commits < 3:
        st.html(ui.notice("Too little history to compare",
                          f"This repository has only {n_commits} commit{'s' if n_commits != 1 else ''}; "
                          "a changelog needs a few more.", "info", "c"))
        return

    if not rels:
        st.html(ui.notice("No releases found: a ghost town",
                          "This repository has no tagged releases (git tags), so there are no two versions to compare. "
                          "Compare its most recent commits instead.", "ghost", "c"))
    elif len(rels) == 1:
        st.html(ui.notice("Only one release found",
                          f"{rels[0].name} is the only tag. You can compare it with the latest commits (what is "
                          "unreleased), or look at the most recent commits.", "tag", "c"))
    st.html('<div class="g-gap sm"></div>')
    modes = (["Between releases"] if rels else []) + ["Last N commits"]
    mode = st.radio("Compare", modes, horizontal=True, label_visibility="collapsed")

    a_ref = b_ref = None
    if mode == "Between releases":
        names = [r.name for r in rels]
        c_from, c_to = st.columns(2)
        to_label = c_to.selectbox("To", ["HEAD (unreleased)"] + names, index=1 if len(names) >= 2 else 0)
        b_ref = "HEAD" if to_label.startswith("HEAD") else to_label
        older = names if b_ref == "HEAD" else names[names.index(b_ref) + 1:]
        if older:
            a_ref = c_from.selectbox("From", older, index=0)
        else:
            c_from.caption("There is no earlier release to compare with.")
    else:
        n = st.number_input("How many recent commits", min_value=2, max_value=min(300, n_commits - 1),
                            value=min(30, n_commits - 1), step=5)
        a_ref, b_ref = f"HEAD~{int(n)}", "HEAD"

    if a_ref and st.button("Generate changelog", type="primary", key="gen_changelog"):
        S["cl_req"] = (head, a_ref, b_ref)
    req = S.get("cl_req")
    if not req or req[0] != head or not a_ref:
        return
    _, a_ref, b_ref = req
    if not (cl.ref_exists(repo_path, a_ref) and cl.ref_exists(repo_path, b_ref)):
        st.warning("Those two points aren't both available in this copy of the repository.")
        return

    try:
        with st.spinner("Reading the history between those points…"):
            data = _compare(repo_path, head, a_ref, b_ref)
    except GitError as e:
        st.html(ui.notice("Couldn't compare those two points", str(e), "warning", "e"))
        return
    st.markdown(f"### {md(a_ref)} → {md(b_ref)}")
    shown = f" (showing the newest {len(data['commits'])})" if data["total"] > len(data["commits"]) else ""
    st.caption(f"{data['total']} commits{shown} · {len(data['changes'])} files changed")
    if not data["commits"]:
        st.info("Nothing changed between these two points.")
        return
    summary_slot = st.empty()

    signals = data["signals"]
    if signals:
        st.html(ui.notice(f"{len(signals)} possible breaking change{'s' if len(signals) != 1 else ''}: beware the curses",
                          "“declared” means a commit says so; “possible” is a heuristic.", "web", "e"))
        st.dataframe(pd.DataFrame([{"Level": s.level, "Type": s.kind, "What": s.detail, "Evidence": s.evidence}
                                   for s in signals]), hide_index=True, width="stretch")
    else:
        st.html(ui.notice("No curses detected",
                          "No breaking changes found. This is a heuristic check, so absence isn't proof.", "pumpkin", "a"))

    for cat, commits in data["groups"].items():
        st.html(ui.category_heading(cat, len(commits)))
        st.markdown("\n".join(f"- {md(c.subject)} · `{c.sha[:7]}` · {md(c.author)}" for c in commits[:60]))
        if len(commits) > 60:
            st.caption(f"…and {len(commits) - 60} more.")

    summary = narrate(summary_slot, guides.CHANGELOG_SYSTEM,
                      guides.changelog_prompt(a_ref, b_ref, data["groups"], data["total"], signals),
                      "Gemma is stirring the cauldron…", wide=True)
    st.download_button("Download as Markdown", _markdown_export(a_ref, b_ref, data, summary),
                       file_name=f"changelog-{re.sub(r'[^A-Za-z0-9._-]+', '_', f'{a_ref}-{b_ref}')}.md",
                       mime="text/markdown", key="dl_changelog")
