"""Small HTML building blocks for the screens.

Streamlit strips <svg> (and inline JS) from the HTML it is given, so the SVG artwork lives in the STYLESHEET
instead: each icon is an SVG data-URI used as a CSS mask, and the markup is just `<span class="g-i i-flag">`.
The icons take the colour of the surrounding text. Bar heights and widths are percentage classes (b0..b100,
w0..w100) for the same reason.

Everything that comes from outside (author names, file paths, model text, issue titles) goes through
`esc`/`inline` before it is placed in markup, and the model's text is parsed into a fixed set of tags by
us, never passed through as HTML.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import zlib

esc = html.escape

# ---------------------------------------------------------------- the SVG art (24x24, stroked)

_ICONS = {
    "commit": '<circle cx="12" cy="12" r="3.3"/><path d="M3 12h5.7M15.3 12H21"/>',
    "users": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5"/>'
             '<circle cx="17.2" cy="9" r="2.4"/><path d="M16.3 14.3c2.8.2 4.7 2 4.7 5.2"/>',
    "file": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>',
    "calendar": '<rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
    "calendar-check": '<rect x="3.5" y="5" width="17" height="15.5" rx="2.2"/><path d="M3.5 10h17M8 3v4M16 3v4M9 15l2 2 4-4.2"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.2M12 7.6h.01"/>',
    "folder": '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18z"/>',
    "flag": '<path d="M5.5 21V4M5.5 4.5h11l-2.2 3.8 2.2 3.7h-11"/>',
    "warning": '<path d="M12 3.6 21.4 20H2.6z"/><path d="M12 10v4.4M12 17.3h.01"/>',
    "issue": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1.6" fill="black"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "flame": '<path d="M12 5.4c.6 3 3.9 4.6 3.9 8.4A3.9 3.9 0 0 1 12 17.7a3.9 3.9 0 0 1-3.9-3.9c0-1.5.6-2.5 1.4-3.4.3 1.2 1 1.8 1.8 2 .4-1.8.2-3.6.7-7z"/>',
    "branch": '<circle cx="6.5" cy="5.5" r="2.2"/><circle cx="6.5" cy="18.5" r="2.2"/><circle cx="17.5" cy="9" r="2.2"/>'
              '<path d="M6.5 7.7v8.6M17.5 11.2c0 3-4.5 2.6-10 5.4"/>',
    "scroll": '<path d="M7 4h11v13a3 3 0 0 1-3 3H6a3 3 0 0 0 3-3V6a2 2 0 0 0-2-2z"/><path d="M10 9h5M10 13h5"/>',
    "tag": '<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.4 1.4 0 0 1 0 2l-6.7 6.7a1.4 1.4 0 0 1-2 0z"/><circle cx="8" cy="8" r="1.4"/>',
    # Halloween
    "pumpkin": '<path d="M12 7.2C10.8 5.9 9.4 5.3 8 5.3 5 5.3 3 8.2 3 12s2 7 5 7c1.4 0 2.8-.6 4-1.9 1.2 1.3 2.6 1.9 4 1.9 3 0 5-3.2 5-7s-2-6.7-5-6.7c-1.4 0-2.8.6-4 1.9z"/>'
               '<path d="M12 7.2c0-1.6.7-3 2.2-3.9M8.3 11.2l1.3 1.8H7zM15.7 11.2l1.3 1.8h-2.6zM8.8 15.4c1 1.2 5.4 1.2 6.4 0"/>',
    "ghost": '<path d="M5 20V10.5a7 7 0 0 1 14 0V20l-2.3-1.8L14.3 20 12 18.2 9.7 20l-2.4-1.8z"/>'
             '<circle cx="9.6" cy="10.4" r="1" fill="black"/><circle cx="14.4" cy="10.4" r="1" fill="black"/>',
    "bat": '<path fill="black" stroke="none" d="M12 8 10 6v3.5C8.6 8.3 6.2 7.5 3 8c1.2 1.2 1.6 2.6 1.4 4.2 1-.8 2.2-.9 3.2-.4.6.5 1 1.2 1.2 2 .8-.9 2-1.2 3.2.2 1.2-1.4 2.4-1.1 3.2-.2.2-.8.6-1.5 1.2-2 1-.5 2.2-.4 3.2.4-.2-1.6.2-3 1.4-4.2-3.2-.5-5.6.3-7 1.5V6z"/>',
    "web": '<path d="M0 0l24 24M0 0l24 11M0 0l11 24M0 6q4.5-1.5 6-6M0 12q8-4 12-12M0 18q11-7 18-18"/>',
    "spider": '<ellipse cx="12" cy="14.2" rx="2.7" ry="3.3" fill="black"/><circle cx="12" cy="9.7" r="1.7" fill="black"/>'
              '<path d="M9.8 12.6 6 9.4 3.4 10.8M9.4 14 4.8 13.4 2.8 15.4M9.8 15.6 6.6 18.4 4.6 21M10.8 11.4 8.6 7 6.6 5.6'
              'M14.2 12.6 18 9.4 20.6 10.8M14.6 14 19.2 13.4 21.2 15.4M14.2 15.6 17.4 18.4 19.4 21M13.2 11.4 15.4 7 17.4 5.6"/>',
    "tombstone": '<path d="M6 21V10a6 6 0 0 1 12 0v11z"/><path d="M3 21h18M12 8.4v5.2M9.6 10.8h4.8"/>',
    "skull": '<path d="M12 3.5c-4.4 0-7.5 3-7.5 7 0 2.4 1.1 4.1 2.8 5.2V19h2.2v-1.6h1V19h3v-1.6h1V19h2.2v-3.3c1.7-1.1 2.8-2.8 2.8-5.2 0-4-3.1-7-7.5-7z"/>'
             '<circle cx="9.2" cy="11" r="1.5" fill="black"/><circle cx="14.8" cy="11" r="1.5" fill="black"/><path d="M12 13.2l-.9 1.8h1.8z"/>',
    "cauldron": '<path d="M5 9h14v2.5c0 4.4-2.6 7.5-7 7.5s-7-3.1-7-7.5z"/><path d="M4 9h16M7.5 19l-1 2M16.5 19l1 2M9 6.4c0-1 1-1.2 1-2.4M13.4 6.4c0-1 1-1.2 1-2.4"/>',
    "wand": '<path d="M4 20 14.5 9.5"/><path d="M13 8l3 3M17.5 3v3M16 4.5h3M20.5 9v2.5M19.2 10.2h2.6"/>',
}

# Streamlit's own widgets (tabs, buttons, the view switcher) can only carry plain-text labels, so their icons are
# attached from the stylesheet: widget key (or tab-group key) -> icon names, in order.
VIEW_ICONS = {"Onboarding": "pumpkin", "Explorer": "bat", "Tech debt": "ghost", "Changelog": "scroll"}
BUTTON_ICONS = {"open_repo": "pumpkin", "debt_link": "ghost", "explain_debt": "wand", "scan_ghosts": "ghost",
                "gen_changelog": "scroll", "dl_changelog": "scroll"}
TAB_ICONS = {"debttabs": ["cauldron", "skull", "tombstone", "ghost"]}
CATEGORY_ICONS = {"Features": "pumpkin", "Fixes": "spider", "Performance": "bat", "Refactoring": "branch",
                  "Documentation": "scroll", "Tests": "cauldron", "Build & CI": "wand", "Other": "skull"}
_LOGO = ('<ellipse cx="12" cy="5.6" rx="2.2" ry="3.5"/><ellipse cx="5.6" cy="10" rx="1.9" ry="3.1" transform="rotate(-30 5.6 10)"/>'
         '<ellipse cx="18.4" cy="10" rx="1.9" ry="3.1" transform="rotate(30 18.4 10)"/>'
         '<path d="M8.3 15.6c0-2.3 1.6-3.5 3.7-3.5s3.7 1.2 3.7 3.5c0 2.9-1.5 5.4-3.7 5.4s-3.7-2.5-3.7-5.4z"/>')
SIZES = (14, 16, 17, 18, 20, 22, 24)


def _mask(inner: str, stroked: bool) -> str:
    """An SVG as a CSS `url("data:...")` value."""
    attrs = ("fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'"
             if stroked else "fill='black'")
    svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' {attrs}>{inner.replace(chr(34), chr(39))}</svg>"
    return 'url("data:image/svg+xml,' + urllib.parse.quote(svg, safe="/:=' ") + '")'


def icon(name: str, size: int = 18) -> str:
    name = name if name in _ICONS else "info"
    size = size if size in SIZES else 18
    return f'<span class="g-i i-{name} s{size}" aria-hidden="true"></span>'


def logo(size: int = 22) -> str:
    """A three-toed dinosaur footprint, filled with the brand gradient."""
    size = size if size in SIZES else 22
    return f'<span class="g-logo s{size}" aria-hidden="true"></span>'


def _art_css() -> str:
    rules = [".g-i, .g-logo { display: inline-block; flex: none; vertical-align: -.2em; }",
             ".g-i { background-color: currentColor; -webkit-mask: var(--m) center / contain no-repeat; "
             "mask: var(--m) center / contain no-repeat; }",
             ".g-logo { background: linear-gradient(135deg, #ff7518, #a78bfa); -webkit-mask: var(--m) center / contain no-repeat; "
             f"mask: var(--m) center / contain no-repeat; --m: {_mask(_LOGO, False)}; }}"]
    rules += [f".i-{n} {{ --m: {_mask(inner, True)}; }}" for n, inner in _ICONS.items()]
    rules += [f".s{s} {{ width: {s}px; height: {s}px; }}" for s in SIZES]
    rules += [f".b{n} {{ height: {max(n, 2)}%; }} .w{n} {{ width: {n}%; }}" for n in range(101)]
    rules += [f".g-avatar.h{k} {{ background: hsl({k * 30} 52% 42%); }}" for k in range(12)]
    return "\n".join(rules)


# ---------------------------------------------------------------- text helpers

_CODE = re.compile(r"`([^`\n]{1,120})`")
_BOLD = re.compile(r"\*\*([^*\n]{1,120})\*\*")


def inline(text: str) -> str:
    """Escape, then allow only `code` and **bold**."""
    t = esc(str(text))
    return _BOLD.sub(r"<strong>\1</strong>", _CODE.sub(r"<code>\1</code>", t))


def initials(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name)[:2]
    return "".join(w[0] for w in words).upper() or "?"


def avatar(name: str) -> str:
    return f'<span class="g-avatar h{zlib.crc32(name.encode()) % 12}" aria-hidden="true">{esc(initials(name))}</span>'


# ---------------------------------------------------------------- the guide, as cards

_TONES = ("a", "b", "c", "d", "e", "f")
# Each section of a model-written guide gets an icon that fits the Halloween theme AND the meaning.
_SECTION_ICON = (("what this", "pumpkin"), ("organis", "folder"), ("where to start", "flag"), ("ask", "ghost"),
                 ("tread", "skull"), ("careful", "skull"), ("week", "calendar-check"),
                 ("hurt", "cauldron"), ("what to do", "flag"), ("summary", "scroll"), ("upgrade", "web"))


def parse_guide(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Markdown from the model -> [(title, [("li"|"p", text)])]. Sections without content are dropped."""
    sections: list[tuple[str, list]] = []
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^#{1,4}\s+(.*)$", line)
        if m:
            cur = (m.group(1).strip().strip("*:"), [])
            sections.append(cur)
            continue
        if not line or cur is None:
            continue
        b = re.match(r"^([*\-•]|\d+[.)])\s+(.*)$", line)
        cur[1].append(("li", b.group(2)) if b else ("p", line))
    return [s for s in sections if s[1]]


def _icon_for(title: str) -> str:
    low = title.lower()
    return next((ico for key, ico in _SECTION_ICON if key in low), "info")


def guide_cards(text: str, wide: bool = False) -> str:
    """`wide` stacks the cards one per row instead of a two-column grid."""
    sections = parse_guide(text)
    if not sections:
        body = "".join(f"<p>{inline(p)}</p>" for p in text.splitlines() if p.strip())
        return f'<div class="g-card"><div class="g-body">{body or "<p>No guide was produced.</p>"}</div></div>'
    cards = []
    for i, (title, items) in enumerate(sections):
        lis = "".join(f"<li>{inline(t)}</li>" for k, t in items if k == "li")
        paras = "".join(f"<p>{inline(t)}</p>" for k, t in items if k == "p")
        cards.append(
            f'<section class="g-card"><h4><span class="g-ico t-{_TONES[i % len(_TONES)]}">{icon(_icon_for(title), 17)}</span>'
            f'{esc(title)}</h4><div class="g-body">{paras}{f"<ul>{lis}</ul>" if lis else ""}</div></section>')
    return f'<div class="g-grid{" one" if wide else ""}">{"".join(cards)}</div>'


def guide_skeleton(hint: str = "Gemma is reading the history…") -> str:
    cards = "".join('<div class="g-card"><div class="g-skel w40"></div><div class="g-skel"></div>'
                    '<div class="g-skel w85"></div><div class="g-skel w60"></div></div>' for _ in range(4))
    return f'<div class="g-grid g-loading">{cards}</div><p class="g-hint">{icon("ghost", 16)} {esc(hint)}</p>'


# ---------------------------------------------------------------- hero

def activity_bars(counts: list[int]) -> str:
    """One bar per month, oldest first; the last three are highlighted."""
    n = len(counts)
    top = max(counts + [1])
    bars = "".join(f'<i class="b{round(100 * c / top)}{" hot" if i >= n - 3 else ""}"></i>' for i, c in enumerate(counts))
    return f'<div class="g-activity" role="img" aria-label="Commits per month over the last {n} months">{bars}</div>'


def stat(name: str, value: str, label: str, tone: str) -> str:
    return (f'<div class="g-stat"><span class="g-stat-ico c-{tone}">{icon(name, 22)}</span>'
            f'<div><div class="g-stat-v">{esc(value)}</div><div class="g-stat-l">{esc(label)}</div></div></div>')


def hero(name: str, label: str, stats: list[tuple[str, str, str]], counts: list[int], note: str = "") -> str:
    tones = ("b", "d", "c", "e")
    chips = "".join(stat(n, v, lbl, tones[i % len(tones)]) for i, (n, v, lbl) in enumerate(stats))
    peak = max(counts) if counts else 0
    foot = f'<p class="g-hint g-tight">{esc(note)}</p>' if note else ""
    return (
        '<div class="g-hero">'
        '<span class="g-i i-web g-decor web" aria-hidden="true"></span>'
        '<span class="g-i i-bat g-decor bat a" aria-hidden="true"></span>'
        '<span class="g-i i-bat g-decor bat b" aria-hidden="true"></span>'
        '<span class="g-i i-ghost g-decor ghost" aria-hidden="true"></span>'
        '<span class="g-i i-pumpkin g-decor pumpkin" aria-hidden="true"></span>'
        '<span class="g-hang" aria-hidden="true"><span class="g-i i-spider s22"></span></span>'
        f'<div class="g-hero-text"><div class="g-eyebrow">{logo(16)} Onboarding guide</div>'
        f'<h1>{esc(name)}</h1><div class="g-sub">{esc(label)}</div><div class="g-stats">{chips}</div>{foot}</div>'
        f'<div class="g-hero-art"><div class="g-art-title">Commits per month <span>last {len(counts)} months · peak {peak}</span></div>'
        f'{activity_bars(counts)}</div></div>')


def category_heading(category: str, count: int) -> str:
    """A changelog section heading with its themed icon (bugs are spiders, features are pumpkins...)."""
    return (f'<h4 class="g-cat"><span class="g-ico t-{_TONES[list(CATEGORY_ICONS).index(category) % len(_TONES)] if category in CATEGORY_ICONS else "a"}">'
            f'{icon(CATEGORY_ICONS.get(category, "skull"), 16)}</span>{esc(category)} <span class="g-cat-n">{count}</span></h4>')


def widget_icon_css() -> str:
    """CSS that puts an SVG icon in front of Streamlit's tabs, buttons and view switcher."""
    pseudo = ("content: ''; display: inline-block; flex: none; width: 1.05em; height: 1.05em; margin-right: .5rem; "
              "background-color: currentColor; -webkit-mask: var(--m) center / contain no-repeat; mask: var(--m) center / contain no-repeat;")
    rules = []
    for key, name in BUTTON_ICONS.items():
        rules.append(f".st-key-{key} button::before {{ {pseudo} --m: {_mask(_ICONS[name], True)}; }}")
    for group, names in TAB_ICONS.items():
        for i, name in enumerate(names, 1):
            rules.append(f'.st-key-{group} button[role="tab"]:nth-of-type({i})::before {{ {pseudo} --m: {_mask(_ICONS[name], True)}; }}')
    for i, name in enumerate(VIEW_ICONS.values(), 1):
        rules.append(f".st-key-view button:nth-of-type({i})::before {{ {pseudo} --m: {_mask(_ICONS[name], True)}; }}")
    rules.append(".st-key-nav .st-key-view button, .st-key-debttabs button[role='tab'] { display: inline-flex; align-items: center; }")
    rules.append(".st-key-debttabs button[role='tab'] p { margin: 0; }")
    return "\n".join(rules) + "\n"


def section_title(text: str, icon_name: str = "pumpkin") -> str:
    """A section heading between two lines, with a Halloween icon on each side."""
    return (f'<div class="g-divider">{icon("pumpkin", 16)}{icon("ghost", 16)}'
            f'<span class="g-divider-text">{icon(icon_name, 18)} {esc(text)}</span>{icon("ghost", 16)}{icon("pumpkin", 16)}</div>')


def page_header(title: str, sub: str, icon_name: str) -> str:
    return (f'<div class="g-head"><span class="g-ico t-a big">{icon(icon_name, 22)}</span>'
            f'<div><h2>{esc(title)}</h2><p>{esc(sub)}</p></div></div>')


# ---------------------------------------------------------------- side cards

def card(title: str, icon_name: str, body: str, tone: str = "a") -> str:
    return (f'<section class="g-card"><h4><span class="g-ico t-{tone}">{icon(icon_name, 17)}</span>{esc(title)}</h4>'
            f'<div class="g-body">{body}</div></section>')


def notice(title: str, text: str, icon_name: str = "info", tone: str = "c") -> str:
    """A friendly empty-state or error card."""
    return card(title, icon_name, f"<p>{esc(text)}</p>", tone)


_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def _pills(who: list[tuple[str, int | None]], logins: dict[str, str | None] | None = None) -> str:
    """One pill per person. With a verified GitHub username the pill is a link to that profile."""
    def one(n: str, c: int | None) -> str:
        tip = f"{n}: {c} commits" if c is not None else n
        login = (logins or {}).get(n)
        if login and _LOGIN.match(login):          # checked again here: a bad value can never reach an href
            tip += " · opens their GitHub profile"
            return (f'<a class="g-person link" href="https://github.com/{esc(login)}" target="_blank" '
                    f'rel="noopener noreferrer" title="{esc(tip)}">{avatar(n)}<span>{esc(n)}</span></a>')
        return f'<span class="g-person" title="{esc(tip)}">{avatar(n)}<span>{esc(n)}</span></span>'
    return "".join(one(n, c) for n, c in who)


def people_list(owners: dict[str, list[tuple[str, int]]], overall: dict[str, int] | None = None,
                logins: dict[str, str | None] | None = None, limit: int = 6) -> str:
    """Who to ask, per folder. When the same people cover every folder, say so once instead of repeating them.

    `overall` is each person's real commit total. Summing the per-folder counts would double-count a commit
    that touched two folders, so the collapsed row never does that.
    """
    rows = list(owners.items())[:limit]
    if not rows:
        return '<p class="g-muted">Not enough recent history to say.</p>'
    names = [tuple(n for n, _ in who) for _, who in rows]
    if len(set(names)) == 1:
        people = sorted({n for n, _ in rows[0][1]}, key=lambda n: -(overall or {}).get(n, 0))
        label = "every area" if len(rows) > 1 else rows[0][0]
        note = '<p class="g-muted g-tight">Everyone listed worked across all of it.</p>' if len(people) > 1 else ""
        return (f'<div class="g-row"><code>{esc(label)}</code><div class="g-people">'
                f'{_pills([(n, (overall or {}).get(n)) for n in people], logins)}</div></div>' + note)
    return "".join(f'<div class="g-row"><code>{esc(area)}</code><div class="g-people">{_pills(who, logins)}</div></div>'
                   for area, who in rows)


def issues_list(issues: list[dict], note: str | None) -> str:
    if not issues:
        return f'<p class="g-muted">{esc(note or "No open issues labelled “good first issue” or “help wanted”.")}</p>'
    rows = []
    for it in issues:
        url = str(it.get("url", ""))
        if not url.startswith("https://github.com/"):
            continue
        rows.append(f'<a class="g-issue" href="{esc(url)}" target="_blank" rel="noopener noreferrer">'
                    f'<span class="g-issue-ico">{icon("issue", 16)}</span>'
                    f'<span><b>#{esc(str(it.get("number", "")))}</b> {esc(it.get("title", ""))}</span></a>')
    return "".join(rows)


def bar_row(path: str, fraction: float, right: str) -> str:
    pct = max(3, min(100, round(fraction * 100)))
    return (f'<div class="g-bar-row"><code title="{esc(path)}">{esc(path)}</code>'
            f'<div class="g-meter" aria-hidden="true"><i class="w{pct}"></i></div>'
            f'<span class="g-num">{esc(right)}</span></div>')


def hotspot_rows(hot) -> str:
    if not hot:
        return '<p class="g-muted">Nothing stands out.</p>'
    top = max(h.score for h in hot) or 1
    rows = "".join(bar_row(h.path, h.score / top, f"{h.recent} changes · {h.fixes} fixes") for h in hot)
    return f'<div class="g-bars">{rows}</div>'


def folder_rows(folders) -> str:
    """Every folder with a risk bar, at full height (no inner scrollbar). Sub-folders are indented under their parent."""
    if not folders:
        return '<p class="g-muted">This repository has no folders.</p>'
    top = max((f.risk for f in folders), default=0) or 1
    rows = []
    for f in folders:
        name = f.path.rsplit("/", 1)[-1] if f.depth > 1 else f.path
        pct = round(100 * f.risk / top)
        detail = f"{f.changes} changes · {f.files} file{'s' if f.files != 1 else ''}"
        rows.append(
            f'<div class="g-bar-row g-folder{" sub" if f.depth > 1 else ""}"><code title="{esc(f.path)}">{esc(name)}/</code>'
            f'<div class="g-meter" aria-hidden="true"><i class="w{pct}"></i></div><span class="g-num">{esc(detail)}</span></div>')
    return f'<div class="g-bars g-folders">{"".join(rows)}</div>'


def owner_rows(risky, logins: dict[str, str | None] | None = None) -> str:
    if not risky:
        return '<p class="g-muted">None, or a one-person project.</p>'
    return "".join(
        f'<div class="g-row"><code title="{esc(r.path)}">{esc(r.path)}</code>'
        f'<div class="g-people">{_pills([(r.top_author, r.commits)], logins)}<span class="g-num">{round(r.top_share * 100)}%</span></div></div>'
        for r in risky)


# ---------------------------------------------------------------- styles

CSS = """
/* Halloween: pumpkin orange and witch purple on a near-black purple. */
:root { --g-line: rgba(255,160,90,.20); --g-card: rgba(167,139,250,.07); --g-accent: #ff7518; --g-accent2: #a78bfa; }
.stApp { background: radial-gradient(1100px 480px at 88% -8%, rgba(139,92,246,.24), transparent 60%),
                     radial-gradient(900px 420px at -5% 0%, rgba(255,117,24,.15), transparent 55%), #140b1f; }
.stMainBlockContainer h1, .stMainBlockContainer h2 { letter-spacing: -.015em; }

/* hero */
.g-hero { position: relative; overflow: hidden; display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 1.8rem;
          padding: 1.5rem 1.7rem; border: 1px solid rgba(255,117,24,.35); border-radius: 18px;
          background: linear-gradient(135deg, rgba(255,117,24,.20), rgba(139,92,246,.20)); }
.g-hero > .g-hero-text, .g-hero > .g-hero-art { position: relative; z-index: 1; }
.g-decor { position: absolute; pointer-events: none; z-index: 0; }
.g-decor.web { top: 0; right: 0; width: 150px; height: 150px; color: rgba(255,255,255,.16); transform: scaleX(-1); }
.g-decor.ghost { right: 1.2rem; bottom: .9rem; width: 46px; height: 46px; color: rgba(244,236,255,.30); animation: g-float 5.5s ease-in-out infinite; }
.g-decor.pumpkin { left: -14px; bottom: -16px; width: 96px; height: 96px; color: rgba(255,117,24,.16); transform: rotate(-12deg); }
/* a spider dangling on a thread from the top edge */
.g-hang { position: absolute; top: 0; right: 235px; width: 22px; height: 78px; z-index: 0; pointer-events: none;
          transform-origin: top center; animation: g-sway 4s ease-in-out infinite; }
.g-hang::before { content: ""; position: absolute; left: 50%; top: 0; width: 1px; height: 54px; background: rgba(244,236,255,.38); }
.g-hang .g-i { position: absolute; left: 0; bottom: 0; color: #e9d5ff; }
@keyframes g-sway { 0%, 100% { transform: rotate(-5deg); } 50% { transform: rotate(5deg); } }
@keyframes g-float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-7px); } }
.g-decor.bat { color: rgba(255,117,24,.55); }
.g-decor.bat.a { top: 14px; right: 150px; width: 30px; height: 30px; animation: g-flutter 4.2s ease-in-out infinite; }
.g-decor.bat.b { top: 52px; right: 78px; width: 20px; height: 20px; animation: g-flutter 5.1s ease-in-out -1.6s infinite; }
@keyframes g-flutter { 0%, 100% { transform: translate(0, 0) rotate(-6deg); } 50% { transform: translate(-7px, 6px) rotate(7deg); } }
@media (prefers-reduced-motion: reduce) { .g-decor.bat, .g-decor.ghost, .g-hang { animation: none; } }
.g-eyebrow { display: inline-flex; align-items: center; gap: .45rem; font-size: .72rem; font-weight: 650;
             letter-spacing: .09em; text-transform: uppercase; opacity: .85; }
.g-hero h1 { margin: .35rem 0 0; padding: 0; font-size: 2.1rem; line-height: 1.1; font-weight: 750; }
.g-sub { margin-top: .15rem; font: 500 .82rem ui-monospace, Consolas, monospace; opacity: .65; }
.g-stats { display: flex; flex-wrap: wrap; gap: .6rem; margin-top: 1.1rem; }
.g-stat { display: flex; align-items: center; gap: .65rem; padding: .55rem .95rem .55rem .8rem; border-radius: 12px;
          background: rgba(127,127,127,.12); }
.g-stat-ico { display: inline-flex; }
.g-stat-v { font-size: 1.1rem; font-weight: 720; line-height: 1.1; }
.g-stat-l { font-size: .7rem; opacity: .65; }
.c-a { color: #ff8a3d; } .c-b { color: #a78bfa; } .c-c { color: #a3e635; } .c-d { color: #f472b6; } .c-e { color: #fb7185; }
.g-hero-art { display: flex; flex-direction: column; justify-content: flex-end; min-width: 0; }
.g-art-title { font-size: .78rem; font-weight: 600; margin-bottom: .5rem; }
.g-art-title span { font-weight: 400; opacity: .6; margin-left: .35rem; }
.g-activity { display: flex; align-items: flex-end; gap: 3px; height: 96px; }
.g-activity i { flex: 1; border-radius: 3px 3px 0 0; background: rgba(127,127,127,.38); min-width: 0; }
.g-activity i.hot { background: var(--g-accent); }

/* cards */
.g-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .9rem; }
.g-grid .g-card:first-child { grid-column: 1 / -1; }
.g-grid.one { grid-template-columns: 1fr; }
.g-tight { margin: .5rem 0 0 !important; }
.g-boxhead { display: flex; align-items: center; gap: .6rem; margin: 0 0 .55rem; padding: 0; font-size: .95rem; font-weight: 680; }
.st-key-startbox { border: 1px solid var(--g-line) !important; border-radius: 14px !important; background: var(--g-card);
                   padding: .95rem 1.1rem 1rem !important; gap: 0 !important; }
.st-key-startbox [data-testid="stVerticalBlock"] { gap: .4rem; }
.g-card { border: 1px solid var(--g-line); border-radius: 14px; padding: .95rem 1.1rem 1rem; background: var(--g-card);
          min-width: 0; margin-bottom: 0; }
.g-card h4 { display: flex; align-items: center; gap: .6rem; margin: 0 0 .55rem; padding: 0; font-size: .95rem; font-weight: 680; }
.g-ico { flex: none; width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; }
.g-ico .g-i { vertical-align: 0; }
.g-ico.big { width: 40px; height: 40px; border-radius: 12px; }
.t-a { background: rgba(255,117,24,.18); color: #ff8a3d; }  .t-b { background: rgba(167,139,250,.18); color: #a78bfa; }
.t-c { background: rgba(163,230,53,.15); color: #a3e635; }  .t-d { background: rgba(244,114,182,.16); color: #f472b6; }
.t-e { background: rgba(251,113,133,.16); color: #fb7185; } .t-f { background: rgba(251,191,36,.16); color: #fbbf24; }
.g-body { font-size: .9rem; line-height: 1.5; }
.g-body p { margin: .2rem 0; }
.g-body ul { margin: .1rem 0 0; padding-left: 1.15rem; }
.g-body li { margin: .28rem 0; }
.g-body code, .g-row code, .g-bars code { font-size: .78rem; padding: .06rem .35rem; border-radius: 6px; background: rgba(127,127,127,.17); }
.g-muted { opacity: .65; font-size: .85rem; }
.g-hint { opacity: .6; font-size: .8rem; margin: .6rem 0 0; }
.g-sectiontitle { margin: 1.6rem 0 .7rem; font-size: 1.05rem; font-weight: 700; }
.g-divider { display: flex; align-items: center; gap: .6rem; margin: 1.7rem 0 .8rem; color: #ff8a3d; }
.g-divider::before, .g-divider::after { content: ""; flex: 1; height: 1px; background: linear-gradient(90deg, transparent, rgba(255,117,24,.5), transparent); }
.g-divider-text { display: inline-flex; align-items: center; gap: .45rem; font-size: 1.05rem; font-weight: 700; color: #f4ecff; padding: 0 .2rem; }
.g-divider > .g-i:nth-child(2), .g-divider > .g-i:nth-child(4) { color: rgba(244,236,255,.7); }
.g-gap { height: .9rem; } .g-gap.sm { height: .2rem; }

/* people: the area on the left, the people beside it. Pills never stretch or break mid-name. */
.g-row { display: grid; grid-template-columns: minmax(0, max-content) minmax(0, 1fr); align-items: center; gap: .35rem .9rem;
         padding: .42rem 0; border-top: 1px dashed var(--g-line); }
.g-row:first-child { border-top: 0; }
.g-row code { max-width: 14rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; justify-self: start; }
.g-people { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; min-width: 0; }
.g-person { display: inline-flex; align-items: center; gap: .4rem; max-width: 100%; padding: .14rem .7rem .14rem .16rem;
            border-radius: 999px; background: rgba(127,127,127,.14); font-size: .8rem; line-height: 1.2; }
.g-person > span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
a.g-person.link { color: inherit !important; text-decoration: none !important; cursor: pointer; transition: background .15s, transform .15s; }
a.g-person.link:hover { background: rgba(255,117,24,.28); transform: translateY(-1px); }
a.g-person.link:focus-visible { outline: 2px solid var(--g-accent); outline-offset: 2px; }
.g-avatar { flex: none; width: 22px; height: 22px; border-radius: 50%; display: inline-grid; place-items: center; color: #fff;
            font: 600 10px/1 system-ui, sans-serif; letter-spacing: .02em; }
.g-issue { display: flex; gap: .55rem; padding: .4rem .3rem; border-radius: 8px; color: inherit !important; text-decoration: none !important;
           font-size: .88rem; line-height: 1.35; }
.g-issue:hover { background: rgba(127,127,127,.12); }
.g-issue-ico { color: #a3e635; flex: none; margin-top: .1rem; }
/* Every row shares ONE grid (rows use display: contents), so all the bars start and end at exactly the same x.
   Giving each row its own grid let the columns drift with the length of that row's text. */
.g-bars { display: grid; grid-template-columns: fit-content(16rem) minmax(60px, 1fr) max-content; align-items: center; gap: .6rem 1rem; }
.g-bars .g-bar-row { display: contents; }
.g-bars code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; justify-self: start; max-width: 100%; }
.g-bars .g-num { justify-self: end; }
.g-meter { height: 7px; border-radius: 4px; background: rgba(127,127,127,.2); overflow: hidden; }
.g-meter i { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, #ff7518, #a855f7); }
.g-num { font-size: .75rem; opacity: .7; white-space: nowrap; }
.g-folder.sub code { margin-left: 1.2rem; background: transparent; opacity: .9; }   /* indent the NAME only, never the bar */

/* page header for the other screens */
.g-head { display: flex; align-items: center; gap: .9rem; margin: .2rem 0 1rem; }
.g-head h2 { margin: 0; padding: 0; font-size: 1.5rem; font-weight: 740; }
.g-head p { margin: .1rem 0 0; font-size: .85rem; opacity: .65; }

/* skeleton while Gemma writes */
.g-skel { height: 11px; border-radius: 6px; margin: .55rem 0; width: 100%;
          background: linear-gradient(90deg, rgba(127,127,127,.12) 25%, rgba(127,127,127,.26) 50%, rgba(127,127,127,.12) 75%);
          background-size: 200% 100%; animation: g-shimmer 1.3s linear infinite; }
.g-skel.w40 { width: 40%; height: 14px; } .g-skel.w85 { width: 85%; } .g-skel.w60 { width: 60%; }
@keyframes g-shimmer { to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .g-skel { animation: none; } }

/* "Start here" buttons */
.st-key-start button { justify-content: flex-start; text-align: left; min-height: 0; padding: .42rem .75rem; border-radius: 10px;
                       font: 500 .78rem ui-monospace, Consolas, monospace; }
.st-key-start button p { text-align: left; font: inherit; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-key-start button::before { content: ""; width: 15px; height: 15px; margin-right: .55rem; flex: none; background: currentColor; opacity: .65;
  -webkit-mask: var(--m) center / contain no-repeat; mask: var(--m) center / contain no-repeat; }

/* Scrollbars: slim, in the theme colours, with no arrow buttons. Chromium, Edge and Safari use the
   ::-webkit-scrollbar rules; Firefox (which ignores them) gets scrollbar-color. */
:root { color-scheme: dark; }
::-webkit-scrollbar { width: 11px; height: 11px; background: transparent; }
::-webkit-scrollbar-track { background: rgba(167,139,250,.07); border-radius: 10px; }
::-webkit-scrollbar-thumb { min-height: 40px; border: 2px solid transparent; border-radius: 10px; background-clip: padding-box;
                            background-image: linear-gradient(180deg, #ff7518, #a855f7); }
::-webkit-scrollbar-thumb:hover { background-image: linear-gradient(180deg, #ff9142, #c084fc); }
::-webkit-scrollbar-button { display: none; width: 0; height: 0; }
::-webkit-scrollbar-corner { background: transparent; }
@supports not selector(::-webkit-scrollbar) { * { scrollbar-width: thin; scrollbar-color: #ff7518 rgba(167,139,250,.1); } }

@media (max-width: 900px) {
  .g-hero { grid-template-columns: 1fr; }
  .g-grid { grid-template-columns: 1fr; }
}
""" + _art_css() + "\n.st-key-start button::before { --m: " + _mask(_ICONS["file"], True) + "; }\n" + (
    # Cobwebs in the top-left and bottom-right corners of the whole page. Behind the content (z-index -1 inside
    # an isolated stacking context), never clickable, and faint enough to leave text fully readable.
    ".stApp { isolation: isolate; }\n"
    ".stApp::before, .stApp::after { content: ''; position: fixed; z-index: -1; pointer-events: none; width: 190px; height: 190px;"
    " background: rgba(244,236,255,.10); -webkit-mask: var(--m) center / contain no-repeat; mask: var(--m) center / contain no-repeat;"
    f" --m: {_mask(_ICONS['web'], True)}; }}\n"
    ".stApp::before { top: 0; left: 0; }\n"
    ".stApp::after { bottom: 0; right: 0; transform: rotate(180deg); }\n"
    ".g-cat { display: flex; align-items: center; gap: .6rem; margin: 1.1rem 0 .3rem; padding: 0; font-size: 1.02rem; font-weight: 680; }\n"
    ".g-cat-n { font-size: .75rem; font-weight: 600; padding: .05rem .5rem; border-radius: 999px; background: rgba(127,127,127,.18); }\n"
) + widget_icon_css()
