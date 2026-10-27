# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-27

First public release.

### Added

- Explain any line or section of a file: `git blame` finds the commits, a local Gemma 4 model (through Ollama)
  explains the intent in a fixed format and cites the commits, and says so when no reason is recorded.
- Open public GitHub repositories as a partial clone (history only). File contents are fetched on demand, and
  images, video, audio, fonts and archives are never opened or downloaded. The local copy is deleted when you leave.
- File tree and code viewer with line and range selection and syntax highlighting.
- Onboarding screen: statistics, an activity chart, a model-written day-one guide, files to read first, who to ask
  per folder (with verified GitHub profile links), good first issues, and files that need care.
- Tech debt screen: hotspots, single-owner files, dormant files, an every-folder map, and an opt-in scan for files
  that nothing mentions.
- Changelog screen: grouped commits between two tags or recent commits, suspected breaking changes with evidence,
  a generated summary, and Markdown export.
- Secret redaction for everything read from git.
- Contributor identities are merged across names and emails; bots are excluded.
- Configuration through environment variables: `GITOSAURUS_MODEL`, `GITOSAURUS_OLLAMA_URL`,
  `GITOSAURUS_KEEP_ALIVE`, and an optional `GITHUB_TOKEN` or `GH_TOKEN`.
- Automatic retry of failed model loads and background warm-up of the model.
- Halloween colour theme with SVG artwork.
- Continuous integration on Windows and Linux that compiles every module, imports them all and renders the app
  headlessly.

### Fixed

- Opening a repository no longer fails when Windows briefly locks the freshly cloned folder; the move is retried and,
  if necessary, done as a copy, and a failure now names its cause.
