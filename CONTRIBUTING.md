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
4. Update docs in the same PR as your code change. If your change affects a CLI command, config key, env var, or Docker behavior, update:
   - `README.md` - env var table, CLI reference, setup steps
   - `config.yaml.example` - any new or changed keys
   - `.env.example` - any new or changed env vars
   - `CHANGELOG.md` is updated only in the release commit, not in individual PRs
5. Commit using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `ci:` CI/CD changes
   - `docs:` documentation only
   - `chore:` tooling, deps, or config
6. Open a pull request against `main`

## Testing with Docker

To test against the full container stack locally:

```bash
make docker-build                                  # builds replaytagger:dev
docker compose run --rm replaytagger doctor        # pre-flight check
docker compose run --rm replaytagger run --dry-run # scan without modifying files
```

Set `image: replaytagger:dev` in `docker-compose.yml` while testing; revert to the GHCR image before committing.

## Pull Request Format

```
Summary
- What changed (one bullet per logical change)
- Why it matters or what problem it solves
- Dependencies added or removed

Setup note (optional; include when reviewers need context before testing)
Any prerequisite config, credential changes, or migration steps.

Test plan
- [ ] Specific step with expected outcome
- [ ] Another step; verify X is logged / Y file is created
- [ ] CI lint, type check, and tests pass
```

"Summary" and "Test plan" are plain text headers, not markdown. Docs-only PRs can omit the test plan if there's nothing to run.

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
