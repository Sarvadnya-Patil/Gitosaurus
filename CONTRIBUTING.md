# Contributing to Gitosaurus

Thank you for helping. This project is open to bug reports, fixes, new analysis ideas and documentation.
Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first; it applies to every issue, pull request and discussion.

## Ways to help

- Report a bug or a confusing result. A repository link and the steps you took make it much easier to reproduce.
- Pick an issue labelled `good first issue` or `help wanted`.
- Improve the documentation, including screenshots for the README.
- Try it on Linux or macOS and report what you find. The author has only exercised Windows.

Some starting points that need no deep knowledge of the code:

- Recognise more public-API patterns in `changelog.py` (Go and Rust declarations are only lightly covered).
- Add entry-point detection for more ecosystems in `insights.structure`.
- Make a message clearer, or a heuristic more cautious. False positives in the breaking-change and dead-code
  features are the most valuable thing to report.

## Development setup

```bash
git clone https://github.com/<your-fork>/Gitosaurus.git
cd Gitosaurus
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

You need Python 3.11 or newer and Git 2.44 or newer. To get answers from the model, install Ollama and pull a
Gemma 4 model; see the [README](README.md). The checks that CI runs do not need Ollama or network access.

## Workflow

1. Fork the repository and create a branch from `main`, for example `fix-contributor-count` or `add-go-declarations`.
2. Make a focused change. Several small pull requests are easier to review than one large one.
3. Try the change in the running app on a real public repository, and restart the server first if you changed
   anything under `gitosaurus/`.
4. Run the three checks listed under "Checks" below and make sure they pass.
5. Open a pull request using the template. Describe what changed and why, and exactly how you checked it.

### Commit messages

Use the imperative mood and keep the first line short: `Merge contributor identities by email`, not `Merged` or
`Fixes stuff`. Explain the reason in the body when it is not obvious. Do not use emoji.

## Conventions

- **No emoji anywhere**: not in code, comments, docstrings, documentation, configuration or commit messages. The
  interface uses SVG artwork instead.
- **Comments explain why, not what.** If a line needs a comment, say what would go wrong without it. Do not narrate
  obvious code.
- **Public functions and classes get a docstring** that says what they return and any caveat a caller must know.
- **Keep git access in one place.** Everything that runs `git` goes through `git_history._git` (or the helpers in
  `repo.py`) so that credentials prompts are disabled and output is decoded consistently.
- **Never read file contents when the history is enough.** The analysis features are built so that they download
  nothing; use `--no-renames` with `git log` and `git diff`, because rename detection reads file contents.

## Things that are easy to get wrong

**Streamlit strips inline SVG.** Any `<svg>` placed in HTML given to `st.html` or `st.markdown` is silently removed.
Icons are therefore defined once in `gitosaurus/ui.py` as SVG data-URIs used as CSS masks, and the markup uses
`<span class="g-i i-name">`. To add an icon, add its drawing to `_ICONS` and make sure it is well-formed SVG (a typo
produces a silently blank icon). Streamlit's own widgets (tabs, buttons, the view switcher) can only have plain-text labels, so their icons are
attached from the stylesheet by widget key; see `BUTTON_ICONS`, `TAB_ICONS` and `VIEW_ICONS`.

**Streamlit does not reload imported modules.** It reloads `app.py` when it changes, but a module such as
`gitosaurus/views.py` stays cached in the running server. Restart `streamlit run` after changing anything under
`gitosaurus/`, or you will see errors that do not exist in the code.

**Windows quirks.** Text-mode pipes turn `\n` into `\r\n`, which corrupts object ids sent to git; send bytes. Paths
longer than 260 characters fail in many tools.

**Escape everything that comes from outside.** Author names, file paths, commit messages, issue titles and model
output must go through `ui.esc` or `ui.inline` before they reach markup. When you add a new place that shows outside
text, try it with a value such as `<img src=x onerror=alert(1)>` and confirm it appears as plain text.

## Checks

The repository does not include an automated test suite, so CI runs three checks on Windows and Linux. Run the same
ones before opening a pull request:

```bash
python -m compileall -q app.py gitosaurus
python -c "import pkgutil, importlib, gitosaurus; [importlib.import_module(m.name) for m in pkgutil.walk_packages(gitosaurus.__path__, 'gitosaurus.')]"
python -c "from streamlit.testing.v1 import AppTest; at = AppTest.from_file('app.py', default_timeout=60).run(); assert not at.exception, at.exception"
```

They catch syntax errors, broken imports and a screen that crashes on load. They do not check behaviour, so also
exercise your change by hand. When you change a heuristic (breaking changes, dead code, hotspots), try one case that
should be flagged and one that must not be, and say what you tried in the pull request.

## Reviewing and merging

A maintainer will review as soon as they can. Expect questions; they are about the change, not the person. Pull
requests are merged once CI passes and a maintainer approves.

## Security issues

Please do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).

## Licensing

By contributing you agree that your contribution is licensed under the project's [MIT license](LICENSE).
