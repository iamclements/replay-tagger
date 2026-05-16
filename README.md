# ReplayTagger

Automatically tag NVIDIA Instant Replay clips with game metadata and sync them into organized Plex collections — with optional YouTube archiving.


[![CI](https://github.com/iamclements/replay-tagger/actions/workflows/ci.yml/badge.svg)](https://github.com/iamclements/replay-tagger/actions/workflows/ci.yml)
[![Security Scan](https://github.com/iamclements/replay-tagger/actions/workflows/security.yml/badge.svg)](https://github.com/iamclements/replay-tagger/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue)](https://github.com/iamclements/replay-tagger/pkgs/container/replaytagger)

---

## How It Works

```
Game Clips/
├── Apex Legends/
│   ├── clip1.mp4   ← genre tag set to "Apex Legends" by ReplayTagger
│   └── clip2.mp4
└── Cyberpunk 2077/
    └── clip1.mp4   ← genre tag set to "Cyberpunk 2077"
```

1. NVIDIA Instant Replay saves clips into per-game folders
2. Syncthing (or any sync tool) delivers them to the machine running ReplayTagger
3. ReplayTagger detects the new file, reads the folder name, and writes it into the video's genre metadata using ffmpeg — without re-encoding
4. Plex reads the genre tag and places the clip into the correct game collection automatically
5. Optionally, clips are uploaded to YouTube as private/unlisted/public archives

---

## Quick Start

### Docker (Recommended)

```bash
# 1. Copy and edit your config
cp config.yaml.example config.yaml
cp .env.example .env
# Edit .env to set CLIPS_DIR and PLEX_TOKEN

# 2. Start the container (watch mode runs forever)
docker compose up -d

# 3. Check logs
docker compose logs -f
```

The container mounts your clips folder, processes any untagged files immediately, then watches for new arrivals.

### Local / Windows

```bash
pip install replaytagger

# Process all clips once
replaytagger --config config.yaml run

# Watch mode
replaytagger --config config.yaml watch
```

---

## Installation

### Requirements

| Component | Version |
|-----------|---------|
| Docker + Docker Compose | 24+ |
| *or* Python | 3.11+ |
| ffmpeg | any recent |

### Docker Image

Pre-built multi-arch images (`amd64` + `arm64`) are published to GitHub Container Registry on every release:

```bash
docker pull ghcr.io/danielclements/replaytagger:latest
```

---

## Configuration

Copy the example files:

```bash
cp config.yaml.example config.yaml
cp .env.example .env
```

### config.yaml

```yaml
clips_dir: /clips          # mapped via Docker volume
extensions: [.mp4, .mkv, .mov]

plex:
  enabled: true
  url: http://192.168.1.100:32400
  library_name: "Game Clips"
  auto_scan: true
  auto_create_collections: true

youtube:
  enabled: false            # set true to enable uploads
  auto_upload: false        # upload automatically in watch mode
  privacy: private
  compress: true
  resolution: 1080
  crf: 28
```

See [config.yaml.example](config.yaml.example) for all options with inline documentation.

### Secrets (.env)

```bash
PLEX_TOKEN=your_plex_token_here   # https://support.plex.tv/articles/204059436
PLEX_URL=http://192.168.1.100:32400
CLIPS_DIR=/path/to/game/clips
```

Secrets are passed as environment variables — never stored in `config.yaml` or committed to git.

---

## CLI Reference

```
replaytagger [--config PATH] [--dry-run] COMMAND

Commands:
  run           Scan all clips once, tag untagged files, then exit
  watch         Watch for new clips and process them as they arrive
  upload FILE   Upload a single clip to YouTube
  youtube-auth  Run the YouTube OAuth2 flow (opens browser)
  status        Show statistics from the state database
```

```bash
# Preview what would be tagged without changing anything
replaytagger --dry-run run

# Upload a specific clip as unlisted
replaytagger upload "clips/Apex Legends/clip1.mp4" --privacy unlisted

# Check tagging and upload counts
replaytagger status
```

---

## YouTube Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **YouTube Data API v3**
3. Create an OAuth 2.0 **Desktop app** credential and download `client_secret.json`
4. Rename it to `youtube_credentials.json` and place it in the project root
5. Run the auth flow (opens a browser):
   ```bash
   replaytagger youtube-auth
   ```
6. Enable YouTube in `config.yaml`:
   ```yaml
   youtube:
     enabled: true
     auto_upload: false   # set true to upload automatically in watch mode
     privacy: private
   ```

Clips are compressed with ffmpeg before uploading to reduce bandwidth. Upload IDs are stored in the state database so files are never uploaded twice.

---

## NAS Deployment

### Synology (Container Manager)

1. Pull `ghcr.io/danielclements/replaytagger:latest`
2. Create a container with:
   - Volume: `/your/clips/folder` → `/clips`
   - Volume: `/your/data/folder` → `/app/data`
   - Volume: `/your/config.yaml` → `/app/config.yaml` (read-only)
   - Environment variables from `.env`

### TrueNAS SCALE / Unraid / Any Docker Host

```bash
docker compose up -d
```

The `arm64` image supports Raspberry Pi and most NAS SoCs natively.

---

## Setting Up Plex Collections

ReplayTagger can create smart collections automatically (`auto_create_collections: true`), or you can set them up manually:

1. Open your Plex game clips library
2. Collections → Create Smart Collection
3. Rule: **Genre** → **is** → `Apex Legends`

Enable **"Automatically create collections by genre"** in library advanced settings to have Plex create them for every genre tag — no manual setup needed.

---

## Development

```bash
git clone https://github.com/danielclements/ReplayTagger
cd ReplayTagger
make install       # creates .venv and installs package + dev deps
source .venv/bin/activate
make test          # pytest
make lint          # ruff + mypy
make docker-build  # build image locally
```

See the [Makefile](Makefile) for all available targets.

### Running Tests

```bash
make test           # with coverage summary
make test-cov       # with HTML coverage report
```

### Project Structure

```
replaytagger/
├── cli.py           # Click CLI entry point
├── config.py        # YAML + env var config loading
├── db.py            # SQLite state tracking
├── tagger.py        # ffmpeg/ffprobe genre tagging
├── plex_client.py   # Plex API integration
├── youtube_client.py# YouTube Data API v3 upload
├── watcher.py       # Watchdog file system monitor
└── logging.py       # structlog configuration
```

---

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Use the provided issue templates for [bug reports](.github/ISSUE_TEMPLATE/bug_report.md) and [feature requests](.github/ISSUE_TEMPLATE/feature_request.md).

---

## License

MIT — see [LICENSE](LICENSE).
