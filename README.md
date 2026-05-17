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
docker pull ghcr.io/iamclements/replay-tagger:latest
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
  run            Scan all clips once, tag untagged files, then exit
  watch          Watch for new clips and process them as they arrive
  plex-auth      Plex PIN OAuth flow — prints a token to add to .env
  youtube-auth   YouTube device flow — prints a URL + code, no browser needed
  youtube-sync   Upload all tagged clips that have passed upload_after_days
  upload FILE    Upload a single clip to YouTube
  status         Show tagging and upload counts from the state database
```

```bash
# Preview what would be tagged without changing anything
replaytagger --dry-run run

# Upload a specific clip as unlisted
replaytagger upload "clips/Apex Legends/clip1.mp4" --privacy unlisted

# Manually push all eligible clips to YouTube (ignores upload_after_days delay)
replaytagger youtube-sync

# Check tagging and upload counts
replaytagger status
```

---

## Plex Setup

### Option A — device console / Portainer (no env var needed)

Run the auth flow from the container console or a one-off container:

```bash
docker compose run --rm replaytagger plex-auth
```

Open the printed URL in any browser, sign in, and click **Allow**. The token is saved automatically to `data/plex_token` (your mounted data volume) and loaded on every subsequent start — no environment variable or container restart required.

### Option B — set the token directly

Get your token from the Plex web UI without running any CLI:

1. Open Plex Web and browse to any item in your library
2. Click `···` → **Get Info** → **View XML**
3. Copy the `X-Plex-Token=XXXXX` value from the browser URL
4. Set it in your `.env` or Portainer stack environment:
   ```
   PLEX_TOKEN=your_token_here
   PLEX_URL=http://192.168.1.x:32400
   ```

The env var takes priority over the token file if both are present.

### Enable Plex in config.yaml

```yaml
plex:
  enabled: true
  library_name: "Game Clips"
  auto_scan: true
  auto_create_collections: true
```

The token is permanent and tied to your Plex account.

---

## YouTube Setup

ReplayTagger uses the OAuth2 **device flow** — no browser on the server required. You enter a short code on any device that has a browser.

### 1. Google Cloud setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the **YouTube Data API v3**
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
4. Application type: **TV and Limited Input devices** *(not Desktop app — device flow requires this type)*
5. Download the JSON and save it as `youtube_credentials.json` in your `data/` folder (mapped to `/app/data` inside the container). Alternatively, skip the file and set `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` env vars instead.

### 2. Authorize

```bash
replaytagger --config config.yaml youtube-auth
```

You'll see:

```
============================================================
YouTube Authorization Required
============================================================
  1. Open:  https://www.google.com/device
  2. Enter: XXXX-XXXX
============================================================
(Code expires in 30 minutes)
```

Open the URL on any device, enter the code, and sign in. The token is saved to `data/youtube_token.json` and reused on every subsequent run — you only authorize once.

**Docker:** run `docker compose run --rm replaytagger youtube-auth` and enter the code in your browser as normal. No port forwarding needed.

### 3. Enable in config.yaml

```yaml
youtube:
  enabled: true
  auto_upload: false        # set true to upload automatically in watch mode
  privacy: private          # private | unlisted | public
  upload_after_days: 0      # delay before auto_upload triggers (0 = immediate)
```

### Upload workflow

| Goal | Command |
|------|---------|
| Upload a single clip now | `replaytagger upload "path/to/clip.mp4"` |
| Upload all eligible clips in batch | `replaytagger youtube-sync` |
| Auto-upload in watch mode | Set `auto_upload: true` in config.yaml |

`youtube-sync` ignores the `upload_after_days` delay — useful when you've already reviewed and renamed your clips and want to push them all at once.

Clips are compressed with ffmpeg before uploading to reduce bandwidth. A SHA256 fingerprint of each file is stored in the state database so files are never uploaded twice, even if they are renamed or moved.

---

## NAS Deployment

### Synology (Container Manager)

1. Pull `ghcr.io/iamclements/replay-tagger:latest`
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
git clone https://github.com/iamclements/replay-tagger
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
