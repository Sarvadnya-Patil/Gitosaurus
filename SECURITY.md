# Security policy

## Supported versions

Only the latest commit on the `main` branch is supported. There are no maintained release branches yet.

## Reporting a vulnerability

Please do not report security problems in a public issue.

Use GitHub's private reporting: open the repository's **Security** tab and choose **Report a vulnerability**. If that
is not available, contact a maintainer through their GitHub profile and ask for a private channel. Include:

- what you found and why it matters,
- the steps or a repository link that reproduces it,
- the version or commit you tested.

You can expect an acknowledgement within a few days and a fix or a plan within a reasonable time after that. Please
give us the chance to fix the problem before disclosing it.

## What the application does with untrusted input

Gitosaurus reads data that anyone can publish: repository names, commit messages, diffs, file contents, issue titles
and author names. The design assumes all of it is hostile.

| Risk | Mitigation |
|---|---|
| Malicious repository link (option injection, other hosts) | Links are parsed strictly into `owner/name` with a character allow-list; only `github.com` is used; the clone command passes the URL after `--`. |
| Credential prompts or login windows | Git is run with prompts disabled and credential helpers turned off, so a private repository fails instead of asking. |
| Secrets in old commits reaching the model or the screen | Diffs, messages and code lines are redacted before use. See `gitosaurus/redact.py`. |
| Markup or script injection through names, messages or model output | Everything is HTML-escaped; model text is parsed into a fixed set of tags and never passed through as HTML. |
| Prompt injection from README or commit text | Repository text is fenced as data in prompts and the system prompt tells the model not to follow instructions found in it. |
| Unsafe links | Profile and issue links are only produced for validated GitHub usernames and `https://github.com/` URLs. |
| Deleting the wrong folder | Cleanup refuses any path outside the application's own cache folder. |
| Leaking an API token | `GITHUB_TOKEN` is read from the environment, sent only to `api.github.com`, and never stored, logged or displayed. |

## Known limits

- Redaction is pattern based and will miss unusual secret formats. It is a safety net; rotate any real secret that was
  ever committed.
- A language model can be misled. Answers are labelled as inference where they are one, and cite the commits used.
- The application is intended to run on your own machine. It has no authentication and should not be exposed to an
  untrusted network.
