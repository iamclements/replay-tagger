# Contributing to ReplayTagger

Thank you for your interest in contributing!

## Getting Started

```bash
git clone https://github.com/iamclements/replay-tagger
cd replay-tagger
make install
source .venv/bin/activate
```

## Development Workflow

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Run the full check suite before opening a PR:
   ```bash
   make lint   # ruff + mypy
   make test   # pytest
   ```
4. Commit using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `ci:` CI/CD changes
   - `docs:` documentation only
   - `chore:` tooling, deps, or config
5. Open a pull request against `main`

## Pull Request Format

Write the description as plain prose: 2-4 sentences explaining what changed and why. For PRs that change behavior or add a feature, include a `## Test cases` section with specific shell commands and expected output so reviewers can verify the change manually. Docs-only PRs don't need test cases.

Example:

```
Adds webhook notifications for Discord and generic HTTP endpoints. Four events
are supported (clip_tagged, clip_uploaded, scan_complete, error) with per-webhook
event filtering so large-library users can skip per-clip noise.

## Test cases

- [ ] `make test` passes (covers payload structure, event filtering, error resilience)
- [ ] Add a Discord webhook to config.yaml, run `replaytagger run`, verify embed appears
- [ ] Remove the webhook URL, confirm tagging still completes without error
```

## Code Style

- Python 3.11+, formatted with `ruff format`, linted with `ruff check` and `mypy --strict`
- No inline comments unless the WHY is non-obvious
- Tests live in `tests/` and use `pytest` + `pytest-mock`

## Reporting Issues

Use the provided issue templates:
- **Bug Report**: reproduction steps, environment details, error output
- **Feature Request**: problem statement, proposed solution, example usage

## Questions?

Open an issue; happy to discuss before you start coding.
