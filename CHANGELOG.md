# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.7.1] - 2026-08-04

### Fixed
- `Tagger.tag()` skipped any file with a genre tag already set, regardless of value, instead of checking whether it matched the resolved game name. A stale or mismatched genre (carried over from a copied file, or written by other software) meant the file never entered the state database, so it was silently and permanently skipped by every future scan and by `youtube-sync`. The skip now only applies when the existing genre already matches the folder's resolved game name.
- `youtube-sync`'s summary log undercounted skips: the `not_tagged` skip path fell through without incrementing the `skipped` counter and gave no indication of why files were skipped. The `youtube_sync_complete` log line now reports a per-reason breakdown (`already_uploaded`, `not_tagged`, `deferred`).

## [2.7.0] - 2026-06-18

### Added
- `config show` command: prints the effective merged configuration (env vars over `config.yaml` over defaults) with secrets (Plex token, SteamGridDB key, webhook URLs) redacted to `***`, so the output is safe to paste into a bug report.
- `init` command: writes a starter `config.yaml` from the bundled example template and prints the next setup steps; refuses to overwrite an existing file without `--force`.
- `status` now reports a pending YouTube upload count (tagged clips with no `youtube_id` past the `upload_after_days` window) and, when the daily quota has been recorded as exceeded, a reset line showing the midnight-Pacific reset and the next scheduled sync hour.
- ntfy notification type: POSTs a plaintext body with the event details and a `Title` header to a topic URL. Auto-detected from `ntfy.sh` hostnames in the `WEBHOOK_URL` env-var path, the same way Discord is detected.
- `doctor` reports the `ffmpeg` and `ffprobe` versions on their OK lines.

### Changed
- `doctor` and all other commands now fail with a clean one-line message when `config.yaml` is not valid YAML, instead of dumping a Python traceback (`init` still runs so it can overwrite a broken file).

## [2.6.0] - 2026-06-10

### Added
- YouTube upload quota persistence: when the daily quota is exhausted, the timestamp is stored in the SQLite state database. The `watch` command runs an automatic sync pass once per day at a configurable hour (`YOUTUBE_SYNC_HOUR`, default 3am local) so uploads resume after the quota resets at midnight Pacific without manual intervention.
- `youtube-sync --force` flag: bypasses the quota cooldown check and attempts uploads immediately regardless of when the quota was last exceeded.
- `WEBHOOK_URL`, `WEBHOOK_TYPE`, and `WEBHOOK_EVENTS` env vars: configure a single notification webhook without editing `config.yaml`. Type is auto-detected from the URL (discord.com hostname). For multiple webhooks, config.yaml is still supported and env var webhook is appended.
- `GAME_NAME_MAP` env var: JSON string mapping clip folder names to canonical game names (e.g. `'{"Apex Legends Season 20": "Apex Legends"}'`). Merged with and takes precedence over config.yaml `game_name_map`.
- `YOUTUBE_CATEGORY_ID` env var and `category_id` config key: sets the YouTube category for uploaded clips (default: `20` - Gaming).
- `YOUTUBE_TAGS` env var and `tags` config key: comma-separated list of tags applied to every upload alongside the game name (default: `gaming,clips`).

### Fixed
- `youtube-sync` no longer retries on the same quota-exceeded day: after a 429, subsequent calls skip automatically until the Pacific calendar date advances. Use `--force` to override.

## [2.5.0] - 2026-06-09

### Added
- SteamGridDB integration: set `STEAMGRIDDB_API_KEY` (free, no account tier) to automatically fetch portrait artwork from SteamGridDB and upload it to Plex when a new collection is created. Covers Steam, Ubisoft Connect, Battle.net, and community-submitted art for modded/private clients (iW4X, XDefiant, etc.)

### Fixed
- Plex collections were re-created on every run when the existing collection title had different capitalisation than the clip folder name (e.g. "XDefiant" in Plex vs "Xdefiant" as the NVIDIA folder name); ensure_collection now uses a case-insensitive comparison

## [2.4.2] - 2026-06-08

### Fixed
- `uploadLimitExceeded` (HTTP 400) from the YouTube Data API now raises `YouTubeQuotaExceededError` and stops the upload loop instead of logging a per-file error and continuing to attempt every remaining clip
- Suppressed the spurious `file_cache is only supported with oauth2client<4.0.0` warning at startup by passing `cache_discovery=False` to the YouTube API client

## [2.4.1] - 2026-06-04

### Fixed
- Clips that fail ffmpeg tagging (e.g. corrupt file, moov atom not found) are no longer uploaded to YouTube; the auto_upload call is now gated on tagging success
- HTTP 429 (rate limit) from the YouTube Data API now raises `YouTubeQuotaExceededError` and stops the upload loop cleanly instead of crashing with an unhandled `HttpError`

## [2.4.0] - 2026-06-03

### Added
- `status` command now prints a per-game breakdown table: clip count and YouTube upload count per game, ordered by clip count descending
- `YOUTUBE_AUTO_UPLOAD` env var to enable auto-upload in watch mode without editing `config.yaml`
- YouTube quota handling: HTTP 403 quota-exceeded responses are caught and logged with a clear `youtube_quota_exceeded` warning including the reset time; remaining clips are retried on the next run instead of crashing
- File size stability check in watch mode: before processing a new clip the watcher polls the file size twice 2 seconds apart and re-queues if still growing - protects against slow network copies stalling mid-write
- ffmpeg integration tests using real ffmpeg: cover genre tagging, container format preservation (MP4 and MKV), mtime restoration, dry-run, and force-retag
- All supported env vars now listed with defaults in `docker-compose.yml` so the full configuration surface is visible without reading docs

### Fixed
- `.mov` (ProRes, H.264) and `.mkv` clips were silently remuxed into MP4 containers during tagging because the ffmpeg temp file always used a `.mp4` extension; temp file now uses the same extension as the source
- `watch` command built Plex, YouTube, and database clients twice on startup (once for its own use and again inside `ctx.invoke(run)`); clients are now built once and passed directly to the shared `_scan_all()` function
- Plex library scan fired once per clip when a Syncthing backlog arrived in watch mode; scans are now coalesced to at most one per 30 seconds
- YouTube device flow auth prompt was not visible until Ctrl+C in Docker due to stdout buffering; all `print()` calls now use `flush=True`
- YouTube auth crashed with an unhandled `RefreshError` when a token was revoked or expired; now falls back to device flow automatically and re-authenticates
- YouTube HTTP 400 from the device code endpoint showed a raw traceback with no guidance; now raises an actionable error explaining the "TV and Limited Input devices" OAuth client type requirement
- `--version` reported `2.0.0` regardless of installed package version; now reads from package metadata via `importlib.metadata` and stays in sync with `pyproject.toml` automatically after every install
- `chown -R /clips` ran on every container start, adding seconds to startup on large NAS shares and conflicting with Syncthing permission management; entrypoint now only chowns `/app/data`

### Changed
- Removed hardcoded `NVIDIA` tag from YouTube uploads; tags are now `[game_name, "gaming", "clips"]`
- Docker image OCI description label updated from "NVIDIA game clips" to "game clips"
- README intro updated to list NVIDIA, OBS, and AMD ReLive as examples

## [2.3.0] - 2026-05-31

### Added
- `replaytagger health` subcommand: exits 0 if the watcher heartbeat is fresh (less than 120 s old), exits 1 otherwise; replaces the inline `python3 -c` one-liner in the Docker `HEALTHCHECK`
- `config.yaml` is now optional; every setting is available as an environment variable: `PLEX_ENABLED`, `PLEX_LIBRARY_NAME`, `PLEX_AUTO_SCAN`, `PLEX_AUTO_COLLECTIONS`, `DEBOUNCE_SECONDS`
- Doctor PUID/PGID mismatch check: warns when `clips_dir` is owned by a different UID than the running process and prints the correct `PUID` value to set in `.env`
- Doctor clips_dir write probe: verifies the clips directory is writable, not just present
- 11 CLI tests covering `doctor`, `run`, `retag`, `status`, and `health` commands

### Fixed
- `game_name_map` was not applied in `youtube-sync` and `upload` commands; clips now use the mapped game name in YouTube titles and the state database
- Content hash no longer computed for files skipped by the already-tagged check

### Changed
- `config.yaml` volume mount in `docker-compose.yml` is commented out by default; Docker no longer silently creates it as a directory when the file does not exist on the host
- `plex_token_missing` warning now includes the exact `plex-auth` command as an actionable hint
- Docker `HEALTHCHECK` uses `replaytagger health` instead of an inline Python one-liner

## [2.2.0] - 2026-05-17

### Added
- Graceful startup when Plex token is missing or the server is unreachable; tagging continues and a `plex_degraded` warning is logged instead of exiting
- PUID/PGID support via gosu-based entrypoint; the container drops to the specified UID/GID at runtime so tagged files are owned correctly on NAS and shared volume deployments
- Webhook notification system with Discord and generic HTTP support; fires on `clip_tagged`, `clip_uploaded`, `scan_complete`, and `error` events with configurable per-webhook event filters

## [2.1.0] - 2026-05-16

### Added
- YouTube OAuth2 **device flow** (`replaytagger youtube-auth`): prints a URL + short code instead of opening a browser, works in Docker and headless environments. Requires a "TV and Limited Input devices" GCP OAuth client.
- `replaytagger youtube-sync` command: manually upload all tagged clips that have passed the `upload_after_days` threshold, without waiting for watch mode
- `upload_after_days` config option and `YOUTUBE_UPLOAD_AFTER_DAYS` env var: delay before `auto_upload` triggers, giving time to trim/rename clips before they go to YouTube (0 = upload immediately)
- `YOUTUBE_ENABLED` env var: enable/disable YouTube without editing `config.yaml`
- `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` env vars: pass GCP OAuth credentials directly without mounting a credentials JSON file; recommended for Docker/Portainer deployments
- Content hash dedup: SHA256 fingerprint of the first 4 MB of each file stored alongside the YouTube video ID, so clips are never uploaded twice even if renamed or moved between Docker and local paths
- Config validation on startup: missing tokens, invalid privacy values, and bad paths all produce clear error messages and a non-zero exit code instead of failing at runtime
- Docker `HEALTHCHECK`: watcher touches `/app/data/.health` every 30 s; the health check verifies the file is less than 120 s old
- Plex token file persistence: `plex-auth` saves the token to `data/plex_token` automatically; loaded on startup without needing a `PLEX_TOKEN` env var (env var still takes priority if set)

### Changed
- `auto_upload` in watch mode now respects `upload_after_days`; `youtube-sync` always ignores it
- YouTube video title is now the clip filename stem only (removed the `Game | ` prefix)
- `plex-auth` prints the authorization URL before attempting to open a browser, so it works correctly in Docker and headless environments
- Base Docker image changed from `python:3.14-slim` to `python:3.12-slim`; added `apt-get upgrade` and pip upgrade to eliminate Trivy CVEs
- `config.yaml.example` uses relative paths for `data_dir`, `credentials_file`, and `token_file`; resolves correctly in both local dev and Docker (WORKDIR `/app`)

### Removed
- `google-auth-oauthlib` dependency: device flow is implemented with stdlib `urllib`

## [2.0.0] - 2026-05-15

### Added
- Python package (`replaytagger`) as the new cross-platform core
- `replaytagger run`: scan all clips once and exit
- `replaytagger watch`: watch mode that processes clips as Syncthing delivers them
- `replaytagger upload`: upload a single clip to YouTube with configurable privacy
- `replaytagger youtube-auth`: interactive OAuth2 setup for YouTube
- `replaytagger status`: show state DB statistics
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
- Secrets (`PLEX_TOKEN`, YouTube credentials) managed via environment variables; never in config files
- Original file modification timestamps preserved after re-muxing (unchanged behavior, now explicitly tested)

## [1.0.0] - 2025-01-01

### Added
- Bug report and feature request GitHub issue templates
