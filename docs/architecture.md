# Architecture

This note explains how Gitosaurus is put together and why. It complements the README, which covers use.

## The shape of the system

```text
 browser  <---->  Streamlit app (app.py, views.py)  <---->  Ollama (local model)
                        |
                        +--> git (partial clone in .cache/repos/<owner>__<name>)  <---->  github.com
                        +--> GitHub API (optional: profile links, issues)
```

Everything runs on one machine. The model is reached over HTTP at `GITOSAURUS_OLLAMA_URL`. Git talks to GitHub only
when a command needs an object the local copy does not have.

## Why a partial clone

Questions about history need the history, not the files. A partial clone (`--filter=blob:none --no-checkout`) downloads
every commit and folder listing but no file contents. A repository with thousands of file versions then costs about a
megabyte on disk. Git fetches a file lazily the first time a command needs it.

Two consequences shape the code:

- **Analysis must not read contents.** `git log --name-only` is cheap, but rename detection compares contents, which
  would silently download files. Every history query therefore uses `--no-renames`, so that analysing a repository
  leaves the same objects missing as before.
- **Lazy fetching is slow one object at a time.** Blaming a file with many versions would make one request per old
  version. `git_history.fetch_missing` fetches a known set of objects in one request, and `prefetch_file_history` uses
  it to download the recent versions of the file you ask about before blaming it.

## Answering "why does this code exist"

1. `story.explain_range` reads the selected lines at `HEAD` and runs `git blame` over the range, which groups the lines
   by the commit that last changed them.
2. For up to three of those commits it collects the message and the diff limited to that file, truncated, and
   redacted. Other recent commits to the file are added as messages only, to stay inside the 8,192-token context.
3. The prompt asks for a fixed four-line format. The model must quote a stated reason or write "None recorded", and
   must label any inference as one.
4. The answer, the commits and the exact diffs that were sent are shown, so the reasoning can be checked.

## Repository-wide features

`insights.py` loads the newest 3,000 commits once, with the files each touched, and derives everything from that:

- **Hotspot score** = changes in the last year multiplied by (1 + share of those that look like fixes).
- **Knowledge risk**: files with at least five commits where one author made at least 80 percent of them.
- **Dormant files**: source files not touched for 18 months while the project kept moving.
- **Folder map**: every folder to two levels, with changes, files and the risk of the code inside.

`insights.history_totals` separately counts the whole history from commit headers only, so the headline numbers are not
limited to the analysis window. Its commit count includes merges, to match what GitHub shows.

`changelog.py` compares two points. Commit subjects are grouped by type. Breaking-change signals are: an explicit `!`
or `BREAKING CHANGE`; a short list of keywords (ignored for housekeeping commit types such as `docs` and `chore`);
deleted source files; and public declarations that were removed or changed, found by fetching only the changed files
in one request and reading the diff.

`deadcode.py` is the only feature that needs contents. It is opt-in, shows the file count first, fetches the source
and config files in one request, and searches them locally for each file's name. Entry-point names and conventional
locations are excluded to reduce false positives.

## People

Git records a name and an email per commit, not a person. `insights.resolve_identities` joins identities that share an
email, or a name that matches ignoring case, spaces and punctuation, using union-find, and shows the most-used
spelling. GitHub usernames are only attached when certain: from a GitHub noreply email address, or from asking GitHub
who authored a specific commit (`profiles.py`). Names are never guessed into links.

## The interface

- **Streamlit strips inline SVG.** All artwork is therefore defined in `ui.py` as data-URIs used as CSS masks, and
  the markup uses empty `<span>` elements with classes. Bar heights and widths are percentage classes for the same
  reason. Streamlit's own widgets get their icons from stylesheet rules keyed on widget keys.
- **The file tree and code viewer** are a custom Streamlit component written in plain HTML and JavaScript
  (`gitosaurus/viewer/frontend/index.html`). It speaks the component protocol by hand over `postMessage`, so there is
  no build step. It returns the opened file and the selected range.
- **Model-written text is parsed, not trusted.** `ui.parse_guide` turns the model's Markdown into a fixed set of tags
  and escapes the rest.

## Lifecycle, cleanup and concurrency

- A clone is made in a temporary folder and moved into place only when complete, so the real folder never exists
  half-finished. A per-repository lock serialises overlapping opens.
- Each running process leaves a lease file in the clone it uses. Cleanup by another session skips clones with a fresh
  lease, and shutdown cleanup never deletes a clone another live process is using.
- If a repository's folder disappears, the next action rebuilds it instead of failing.

## The model client

`llm.py` is a small standard-library client. It keeps the model loaded for `GITOSAURUS_KEEP_ALIVE`, retries a failed
load (the failed attempt wakes a sleeping GPU, so the retry usually works), and warms the model up in the background
when a repository opens. Warm-up and real requests must use the same context size, or Ollama reloads the model.

## Verification

The repository does not include an automated test suite. Continuous integration compiles every module, imports every
module and renders the app headlessly through Streamlit's `AppTest`, on Windows and Linux. Behaviour that depends on
git (lazy fetching, blame, merge counts) is best checked by running the app against a real public repository.
