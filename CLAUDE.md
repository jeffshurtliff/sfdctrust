# CLAUDE.md — sfdctrust

Claude Code reads this file automatically; it does not read `AGENTS.md` on its own. The canonical,
tool-agnostic guidance is imported below and **always takes precedence**. This file only adds
Claude-specific notes. Keep it short and consistent with `AGENTS.md`.

@AGENTS.md

## Local-only instructions

`local/` is gitignored and may not exist in every checkout. When present, also apply the
workstation addendum (a missing import is ignored):

@local/AGENTS.md

Personal Claude-only notes belong in `CLAUDE.local.md` (gitignored), not in this file.

## Where things stand

- Read `docs/API_CONTRACT.md` before any endpoint, model, auth, or transport work. It is the verified
  operation/schema inventory and records the adopted SDK policies (credentials, ownership, retries,
  models, pagination, errors) and the recommended implementation sequence.
- `local/vendor_docs/mytrust-api.yaml` is the local OpenAPI copy. Read it when needed, but never copy
  it into tracked files or redistribute it.
- `local/Initial Brainstorm with ChatGPT for Salesforce Trust API Project.md` and
  `local/Implementation-Tracker.md` are background only. Where they disagree with `AGENTS.md` or
  `docs/API_CONTRACT.md`, the latter win (for example, the environment variable is `SFDCTRUST_PAT`,
  not `SFDC_STATUS_PAT`; RESPX and pytest-asyncio are not dependencies; example package names such
  as `mytrustcenter` are illustrative).
- Do not read other files under `local/` unless the task needs them, and never read `.env` or other
  credential files.

## Verified commands

Python 3.12, Poetry 2.x, and an in-project `.venv` are in use. Run everything through Poetry:

```sh
poetry run pytest -q
poetry run ruff check .
poetry run ruff format --check <changed files>
poetry run bandit -q -r src
poetry check && poetry build
```

Repository-wide `ruff format --check .` currently flags a few pre-existing files (see
`docs/API_CONTRACT.md`); check only the files you changed and do not reformat others.
Ruff uses single quotes and a 130-character line length.

## Module headers

Python modules use a reStructuredText field header (`:Module:`, `:Synopsis:`, `:Created By:`,
`:Last Modified:`, `:Modified Date:`). When Claude edits a module, set `:Last Modified:` to
`Jeff Shurtliff (via Claude <model name>)` using the name of the model actually running
(e.g. `Jeff Shurtliff (via Claude Opus 5.5)`), and `:Modified Date:` to today's date in
`DD Mon YYYY` format. This overrides the GPT identifier in `local/AGENTS.md`, which applies to
Codex. Only update headers of files you actually change.

## Claude Code behavior in this repo

- Leave changes uncommitted unless asked. Do not create commits, branches, PRs, tags, or releases on
  your own, and never push without explicit approval (`.claude/settings.json` requires a prompt for
  push, release, publish, and repository-settings commands).
- The project uses [Entire](https://docs.entire.io) for session checkpoints via the hooks in
  `.claude/settings.json`. Those hooks are managed by `entire`; do not hand-edit or remove them. Do not
  run `entire enable`, `disable`, `clean`, or `auth` without asking.
- Use web fetching only for official Salesforce, Python, HTTPX, Pydantic, and MCP documentation, and
  say which facts were verified against the current reference versus taken from the local copy.
- Never make live My Trust Center API calls, even if a PAT appears to be available in the environment.
- Use subagents for broad read-only exploration if needed, but keep design decisions and edits in the
  main session so they follow this file.
- Finish every task with the completion handoff described in `AGENTS.md`.

<!-- entire-agent:begin -->
<!-- Entire agent instructions are inherited through AGENTS.md. -->
<!-- entire-agent:end -->
