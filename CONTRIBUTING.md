# Contributing to Gitosaurus

Thank you for helping. This project is open to bug reports, fixes, new analysis ideas, documentation and tests.
Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first; it applies to every issue, pull request and discussion.

## Ways to help

- Report a bug or a confusing result. A repository link and the steps you took make it much easier to reproduce.
- Pick an issue labelled `good first issue` or `help wanted`.
- Improve the documentation, including screenshots for the README.
- Try it on Linux or macOS and report what you find. The author has only exercised Windows.

Some starting points that need no deep knowledge of the code:

- Recognise more public-API patterns in `changelog.py` (Go and Rust declarations are only lightly covered).
- Add entry-point detection for more ecosystems in `insights.structure`.
- Add a language to the sample data in the tests, or a test for an edge case you hit.
- Make a message clearer, or a heuristic more cautious. False positives in the breaking-change and dead-code
  features are the most valuable thing to report.

## Development setup

```bash
git clone https://github.com/<your-fork>/Gitosaurus.git
cd Gitosaurus
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

You need Python 3.11 or newer and Git 2.44 or newer. You do **not** need Ollama to run the tests. To use the
application itself, install Ollama and pull a Gemma 4 model; see the [README](README.md).

Run the app with `streamlit run app.py`.

## Workflow

1. Fork the repository and create a branch from `main`, for example `fix-contributor-count` or `add-go-declarations`.
2. Make a focused change. Several small pull requests are easier to review than one large one.
3. Add or update tests. A bug fix should come with a test that fails without the fix.
4. Run the whole suite with `python -m pytest` and make sure it passes.
5. Open a pull request using the template. Describe what changed and why, and how you checked it.

### Commit messages

Use the imperative mood and keep the first line short: `Merge contributor identities by email`, not `Merged` or
`Fixes stuff`. Explain the reason in the body when it is not obvious. Do not use emoji.

## Conventions

- **No emoji anywhere**: not in code, comments, docstrings, documentation, configuration or commit messages. A test
  enforces this for the source tree. The interface uses SVG artwork instead.
- **Comments explain why, not what.** If a line needs a comment, say what would go wrong without it. Do not narrate
  obvious code.
- **Public functions and classes get a docstring** that says what they return and any caveat a caller must know.
- **Keep git access in one place.** Everything that runs `git` goes through `git_history._git` (or the helpers in
  `repo.py`) so that credentials prompts are disabled and output is decoded consistently.
- **Never read file contents when the history is enough.** The analysis features are built so that they download
  nothing; use `--no-renames` with `git log` and `git diff`, because rename detection reads file contents. A test
  guards this.

## Things that are easy to get wrong

**Streamlit strips inline SVG.** Any `<svg>` placed in HTML given to `st.html` or `st.markdown` is silently removed.
Icons are therefore defined once in `gitosaurus/ui.py` as SVG data-URIs used as CSS masks, and the markup uses
`<span class="g-i i-name">`. To add an icon, add its drawing to `_ICONS`; a test checks that every drawing is valid
XML. Streamlit's own widgets (tabs, buttons, the view switcher) can only have plain-text labels, so their icons are
attached from the stylesheet by widget key; see `BUTTON_ICONS`, `TAB_ICONS` and `VIEW_ICONS`.

**Streamlit does not reload imported modules.** It reloads `app.py` when it changes, but a module such as
`gitosaurus/views.py` stays cached in the running server. Restart `streamlit run` after changing anything under
`gitosaurus/`, or you will see errors that do not exist in the code.

**Windows quirks.** Text-mode pipes turn `\n` into `\r\n`, which corrupts object ids sent to git; send bytes. Paths
longer than 260 characters fail in many tools.

**Escape everything that comes from outside.** Author names, file paths, commit messages, issue titles and model
output must go through `ui.esc` or `ui.inline` before they reach markup. Tests in `tests/test_ui.py` check that
injected tags and attributes never survive; add one for any new output.

## Tests

- Tests build real repositories with real `git` commands (see `tests/conftest.py`: `make_repo` and
  `partial_clone`). Prefer that over mocking git.
- Tests must not use the network. GitHub calls and the model are stubbed.
- Whole-screen tests use Streamlit's `AppTest` against a local repository (`tests/test_screens.py`).
- When you change a heuristic, add a case that should be flagged and one that must not be.
- If a test seems to pass too easily, break the code on purpose and confirm that it fails.

## Reviewing and merging

A maintainer will review as soon as they can. Expect questions; they are about the change, not the person. Pull
requests are merged once the tests pass in CI and a maintainer approves.

## Security issues

Please do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).

## Licensing

By contributing you agree that your contribution is licensed under the project's [MIT license](LICENSE).
