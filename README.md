# Gitosaurus

Ask any line of code why it exists.

Gitosaurus opens a public GitHub repository, lets you browse it like GitHub does, and answers "why is this here?"
for any line or section by reading that code's git history and asking a local Gemma 4 model to explain the intent.
Every answer cites commit hashes and says plainly when the history does not record a reason. Nothing leaves your
machine except the requests to GitHub and to your own Ollama server.

It also turns a repository's history into three more tools:

- **Onboarding**: a day-one guide for a new contributor, who to ask about each area, and where to tread carefully.
- **Tech debt and dead code**: hotspots, single-owner files, dormant files and files that nothing mentions.
- **Changelog and breaking changes**: release notes between two tags, with each suspected breaking change shown with its evidence.

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Running it](#running-it)
- [Using it](#using-it)
- [Configuration](#configuration)
- [Privacy and security](#privacy-and-security)
- [Project layout](#project-layout)
- [Development and checks](#development-and-checks)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)

## How it works

1. You paste a link to a public GitHub repository.
2. Gitosaurus makes a **partial clone**: commits and folder listings only, with no file contents and no working
   copy. Git then fetches single files from GitHub on demand, when you open one or ask about it, and fetches the
   recent versions of the file you ask about in one batch. Images, video, audio, fonts, archives and other binaries
   are shown greyed out and are never opened or downloaded.
3. For a question about lines 40 to 52 of a file, `git blame` finds the commits that last changed them. Their
   messages, redacted diffs and nearby history go to a local Gemma 4 model through Ollama, which answers in a fixed
   format: what changed, the stated reason (or "None recorded"), a clearly labelled inference, and the sources.
4. When you leave the repository, or open a different one, the local copy is deleted.

More detail is in [docs/architecture.md](docs/architecture.md).

## Requirements

| Requirement | Notes |
|---|---|
| Python 3.11 or newer | Developed on 3.14. |
| Git 2.44 or newer | Needed for `git --no-lazy-fetch`. Developed on 2.51. |
| [Ollama](https://ollama.com) | Runs the model locally. Developed on 0.40. |
| A Gemma 4 model in Ollama | `gemma4:e4b` by default, about 6.6 GB on disk. |
| Streamlit 1.66 or newer | Installed by `requirements.txt`. |

A GPU is not required, but a model on the CPU answers much more slowly. The default model uses roughly 4 GB of
system memory while loaded, even when it runs on a GPU.

## Installation

```bash
git clone https://github.com/<your-account>/Gitosaurus.git
cd Gitosaurus

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt
```

Install Ollama from <https://ollama.com>, then pull the model:

```bash
ollama pull gemma4:e4b
```

Check the exact tag names available to you with `ollama list` or on the Ollama model library. Gemma models are
distributed under their own license; read the terms of the model you pull.

## Running it

```bash
streamlit run app.py
```

Streamlit prints a local address, normally <http://localhost:8501>. Paste a public repository link, for example
`https://github.com/expressjs/cors`, and press **Open repository**. Opening a repository also starts loading the model
in the background so that your first question is faster.

Streamlit reloads `app.py` when it changes but not the modules it imports. If you edit anything under `gitosaurus/`,
restart the server.

## Using it

The bar at the top switches between four screens.

**Onboarding** is the default. It shows commit, contributor and file counts, a chart of recent activity, a guide
written by the model from the repository's own facts, a list of files to read first, the people who changed each
folder most in the last year (linked to their GitHub profiles when that can be verified), open "good first issue"
items, and the files that need care.

**Explorer** is a file tree and code viewer. Click a line number to select a line; shift-click or drag to select a
section of up to 80 lines. Then press **Dig it up** to see the explanation and the commits behind it. The answer
opens in a popup, and the "What was sent to the model" panel shows exactly which text was used, with secrets masked.

**Tech debt** has four tabs: hotspots (files that change often and often to fix something), knowledge risk (files
almost always changed by one person), dormant files, and an opt-in scan for files that no other file mentions. The
last tab downloads the repository's source and config files in one request and shows you how many before it starts.
Results are candidates to investigate, not verdicts.

**Changelog** compares two releases (git tags), a release against the latest commits, or just the most recent
commits. It groups commits by type, lists suspected breaking changes with their evidence, and can write a short
summary and upgrade notes. The result can be downloaded as Markdown. A repository with no tags gets a clear message
and the commit-range option.

### Command line

A single explanation can also be produced without the interface, against any local clone:

```bash
python -m gitosaurus.cli <path-to-repo> <file/in/repo> <first-line> [last-line] [--model TAG]
```

## Configuration

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GITOSAURUS_MODEL` | `gemma4:e4b` | Ollama model tag used for every answer. |
| `GITOSAURUS_OLLAMA_URL` | `http://localhost:11434` | Address of the Ollama server. |
| `GITOSAURUS_KEEP_ALIVE` | `30m` | How long Ollama keeps the model loaded after the last request (`5m`, `30m`, `-1` for always). A longer value avoids slow cold starts; a shorter value frees about 4 GB of memory sooner. |
| `GITHUB_TOKEN` or `GH_TOKEN` | unset | Optional. Raises GitHub's API limit from 60 to 5,000 requests per hour. Used only for requests to `api.github.com`; never stored, logged or shown. Without it, profile links and issue lists can stop working after heavy use. |

Example (PowerShell):

```powershell
$env:GITOSAURUS_MODEL = "gemma4:e2b"
streamlit run app.py
```

### Theme

The colour theme lives in [.streamlit/config.toml](.streamlit/config.toml). The icons and decorations are defined in
[gitosaurus/ui.py](gitosaurus/ui.py).

### Built-in limits

These are constants in the source, listed here so that behaviour is not a surprise.

| Limit | Value | Where |
|---|---|---|
| Commits analysed in detail | most recent 3,000 | `insights.MAX_COMMITS` |
| Whole-history counts | up to 200,000 commits | `insights.TOTALS_CAP` |
| Largest repository opened | about 300 MB (as reported by GitHub) | `repo.MAX_REPO_KB` |
| Largest file displayed | 300 KB | `repo.MAX_FILE_BYTES` |
| Section selected for one question | 80 lines | `story.MAX_SECTION_LINES` |
| Files read by the unreferenced-files scan | 400 | `deadcode.MAX_SCAN_FILES` |
| Model context window | 8,192 tokens | `llm.NUM_CTX` |

## Privacy and security

- The model runs on your machine. Prompts are sent to your Ollama server only.
- Gitosaurus talks to two outside services: GitHub (to clone public repositories and, optionally, for profile and
  issue lookups) and nothing else.
- Everything read from git (diffs, commit messages, code lines) is passed through a redaction step before it reaches
  the model or the screen. It masks connection-string passwords, common cloud and API token formats, JWTs, private
  keys and `password = "..."` style values. It deliberately over-masks and is a safety net, not a replacement for
  rotating a leaked secret.
- Text that comes from a repository (README, commit messages, issue titles) is treated as untrusted. It is fenced as
  data in prompts, and everything shown in the interface is HTML-escaped.
- Only public GitHub repositories can be opened, and links are validated before anything is run.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Project layout

```text
app.py                  Streamlit entry point: navigation, repository lifecycle, screens
gitosaurus/
  repo.py               opening a repository: link parsing, partial clone, cleanup, browsing, GitHub API calls
  git_history.py        blame, commit details, batched file fetching (all git access)
  insights.py           repository-wide facts: hotspots, people, folders, identity merging
  changelog.py          commits between two points and breaking-change signals
  deadcode.py           the opt-in scan for files that nothing mentions
  story.py              builds the prompt for "why does this code exist"
  guides.py             prompts for the onboarding guide, changelog summary and debt summary
  llm.py                Ollama client: retries, keep-alive, warm-up
  redact.py             secret masking
  profiles.py           links people to GitHub profiles, only when verified
  highlight.py          syntax highlighting
  ui.py                 HTML and stylesheet building blocks, including every SVG icon
  views.py              the Onboarding, Tech debt and Changelog screens
  viewer/               custom Streamlit component: file tree and code viewer (plain HTML and JavaScript)
  assets/               favicon
docs/                   architecture notes
```

## Development and checks

This repository does not include an automated test suite (the `tests/` folder is listed in `.gitignore`). Continuous
integration instead runs three checks on Windows and Linux, which you can run yourself:

```bash
python -m compileall -q app.py gitosaurus          # every module compiles
python -c "import pkgutil, importlib, gitosaurus; [importlib.import_module(m.name) for m in pkgutil.walk_packages(gitosaurus.__path__, 'gitosaurus.')]"
python -c "from streamlit.testing.v1 import AppTest; at = AppTest.from_file('app.py', default_timeout=60).run(); assert not at.exception, at.exception"
```

The last command starts the app headlessly and fails if rendering raises. None of the checks need Ollama or network
access. Beyond them, the way to verify a change is to run the app (`streamlit run app.py`) and try it on a real
repository.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow, conventions and a few things that are easy to get wrong
(Streamlit strips inline SVG, and does not reload imported modules).

## Troubleshooting

**"Ollama couldn't run the model (HTTP 500)".** The model's runner crashed while loading. On laptops with a hybrid
GPU this often happens on the first load after the GPU has gone to sleep; Gitosaurus retries automatically and warms
the model up when a repository opens. If it persists, check free memory, restart Ollama, or try a smaller model with
`GITOSAURUS_MODEL`.

**Ollama uses the CPU although a GPU is present.** Ollama detects GPUs when it starts. Restart the Ollama server after
enabling or waking the GPU.

**"Cannot reach Ollama".** Start Ollama, or set `GITOSAURUS_OLLAMA_URL` to where it is running.

**Profile links or issues are missing.** GitHub's anonymous API allows 60 requests per hour. Set `GITHUB_TOKEN`, or
wait. Gitosaurus shows a note when it was rate limited.

**The first answer is slow.** The first request loads the model into memory. Raise `GITOSAURUS_KEEP_ALIVE` to keep it
loaded between questions.

**"No such file or directory" for the repository folder.** The local copy was removed (for example by another browser
tab). Gitosaurus rebuilds it automatically on the next action.

## Limitations

- Public GitHub repositories only. Private repositories and other hosts are not supported.
- Detailed analysis covers the most recent 3,000 commits; whole-history counts cover more.
- The contributor count is the number of distinct people in the git history (names and emails merged, bots left
  out). GitHub counts accounts, which git does not record, so GitHub's figure can differ a little.
- "Breaking change", "dormant" and "unreferenced" results are heuristics. They point to places worth a look and can
  be wrong.
- A model can still misread history. Answers are grounded in the supplied commits and say when no reason is recorded,
  but they should be checked against the linked commits.
- Tested on Windows. Linux and macOS are expected to work but have not been exercised by the author.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) first. Issues labelled `good first issue` are a good place to start.

## License

MIT. See [LICENSE](LICENSE).
