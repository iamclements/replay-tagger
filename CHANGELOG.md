# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- YouTube OAuth2 **device flow** (`replaytagger youtube-auth`) — prints a URL + short code instead of opening a browser, works in Docker and headless environments. Requires a "TV and Limited Input devices" GCP OAuth client.
- `replaytagger youtube-sync` command — manually upload all tagged clips that have passed the `upload_after_days` threshold, without waiting for watch mode
- `upload_after_days` config option and `YOUTUBE_UPLOAD_AFTER_DAYS` env var — delay before `auto_upload` triggers, giving time to trim/rename clips before they go to YouTube (0 = upload immediately)
- `YOUTUBE_ENABLED` env var — enable/disable YouTube without editing `config.yaml`
- Content hash dedup — SHA256 fingerprint of the first 4 MB of each file stored alongside the YouTube video ID, so clips are never uploaded twice even if renamed or moved between Docker and local paths
- Config validation on startup — missing tokens, invalid privacy values, and bad paths all produce clear error messages and a non-zero exit code instead of failing at runtime
- Docker `HEALTHCHECK` — watcher touches `/app/data/.health` every 30 s; the health check verifies the file is less than 120 s old

### Changed
- `auto_upload` in watch mode now respects `upload_after_days`; `youtube-sync` always ignores it
- YouTube video title is now the clip filename stem only (removed the `Game | ` prefix)

### Removed
- `google-auth-oauthlib` dependency — device flow is implemented with stdlib `urllib`

## [2.0.0] - 2026-05-15

### Added
- Python package (`replaytagger`) as the new cross-platform core
- `replaytagger run` — scan all clips once and exit
- `replaytagger watch` — watch mode that processes clips as Syncthing delivers them
- `replaytagger upload` — upload a single clip to YouTube with configurable privacy
- `replaytagger youtube-auth` — interactive OAuth2 setup for YouTube
- `replaytagger status` — show state DB statistics
- `--dry-run` global flag to preview changes without modifying files
- SQLite state database (`data/state.db`) to track tagged files and YouTube upload IDs
- ffprobe-based genre detection (replaces ffmetadata parsing)
- Plex API integration: on-demand library scan and smart collection creation
- YouTube Data API v3 upload with resumable chunked upload and pre-upload compression
- Watchdog-based file watcher with configurable debounce (handles Syncthing write delays)
- Multi-stage Dockerfile with non-root user, ffmpeg, and VOLUME declarations
- `docker-compose.yml` for one-command deployment on any Docker host (Synology, TrueNAS SCALE, Unraid, Linux)
- Multi-arch Docker images (`linux/amd64`, `linux/arm64`) published to GHCR on version tags
- GitHub Actions CI: lint (ruff + mypy), test matrix (Python 3.11 & 3.12), Docker build validation
- GitHub Actions release: multi-arch image push to GHCR + GitHub Release with changelog notes
- GitHub Actions security: weekly Trivy container/repo scan + pip-audit, results in Security tab
- Dependabot configuration for pip, GitHub Actions, and Docker dependency updates
- `CODEOWNERS` file for automatic PR review assignments
- `Makefile` with `install`, `lint`, `format`, `test`, `docker-build`, `docker-up`, `run`, `watch`
- `config.yaml.example` with fully documented configuration options
- `.env.example` for environment variable reference
- Structured JSON logging via `structlog` (switchable to pretty text for development)

### Changed
- Configuration moved from hardcoded script variables to `config.yaml` + environment variables
- Secrets (`PLEX_TOKEN`, YouTube credentials) managed via environment variables — never in config files
- Original file modification timestamps preserved after re-muxing (unchanged behavior, now explicitly tested)

## [1.0.0] - 2025-01-01

### Added
- Bug report and feature request GitHub issue templates
