<p align="center">
  <img src="docs/images/logo.svg" width="80" alt="ReplayTagger logo">
</p>

# ReplayTagger

Automatically tag NVIDIA Instant Replay clips by game and organize them into Plex collections — with optional YouTube archiving.

[![CI](https://github.com/iamclements/replay-tagger/actions/workflows/ci.yml/badge.svg)](https://github.com/iamclements/replay-tagger/actions/workflows/ci.yml)
[![Security Scan](https://github.com/iamclements/replay-tagger/actions/workflows/security.yml/badge.svg)](https://github.com/iamclements/replay-tagger/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue)](https://github.com/iamclements/replay-tagger/pkgs/container/replay-tagger)

![Gaming Clips collections in Plex](docs/images/banner.png)

---

## The idea

NVIDIA saves clips — whether triggered by hotkey or recorded as a full session — into folders named after the game you were playing. ReplayTagger watches those folders and writes the game name into each clip's genre metadata using ffmpeg. Plex reads that tag and automatically places each clip into the right game collection.

**Your video files are not re-encoded.** Only a small metadata field is updated, and original timestamps are preserved.

YouTube archiving is an optional bonus. Clips are compressed before upload (YouTube's storage is free, and compressed is better than nothing), and each file is fingerprinted so it's never uploaded twice even if you rename it.

---

## What you need

- **A gaming PC** with [NVIDIA GeForce Experience](https://www.nvidia.com/en-us/geforce/geforce-experience/) — clips saved via hotkey or session recording
- **A homelab server or NAS** running Docker — this is where ReplayTagger and Plex live (Synology, Unraid, TrueNAS SCALE, Raspberry Pi, or any Linux machine)
- **Plex Media Server** already running on that server
- **A way to get clips to your server** — [Syncthing](https://syncthing.net/) is the easiest option (see [Step 2](#step-2--get-your-clips-to-the-server))

> **ReplayTagger runs on your server, not your gaming PC.** It sits next to Plex and watches the folder where your clips land.

Optional: a Google account for YouTube archiving.

---

## How it works

NVIDIA GeForce Experience organizes clips by game:

```
Videos/
├── Apex Legends/
│   ├── clip1.mp4   ← tagged "Apex Legends"
│   └── clip2.mp4
└── Cyberpunk 2077/
    └── clip1.mp4   ← tagged "Cyberpunk 2077"
```

![Flow diagram](docs/images/flow-diagram.svg)

1. NVIDIA saves a clip to a per-game folder on your gaming PC
2. A sync tool (e.g. Syncthing) delivers it to your server
3. ReplayTagger detects the new file and writes the game name into the genre tag
4. Plex reads the tag and adds the clip to the matching game collection

---

## Setup

### Step 0 — Get the files

Clone the repo **on the machine that will run the container** — not your gaming PC:

```bash
git clone https://github.com/iamclements/replay-tagger
cd replay-tagger
```

---

### Step 1 — Create a Plex library

1. Plex Web → **Libraries** → **Add Library**
2. Type: **Movies** (Home Videos doesn't support genre-based collections)
3. Name it — e.g. `Gaming Clips` — note the exact name
4. Point it at the folder where clips will land
5. **Advanced** tab → **"Automatically create collections"** → **"by Genre"**

Note the library name — it goes into `config.yaml` in Step 3.

> **If the library name in config.yaml doesn't match exactly, ReplayTagger will start but Plex scans and collection creation will silently do nothing.** Check the logs if clips aren't appearing.

---

### Step 2 — Get your clips to the server

**Where NVIDIA saves clips**

By default, NVIDIA GeForce Experience saves to:
```
C:\Users\<your-username>\Videos\
```
Each game gets its own subfolder automatically.

**Syncing to your server**

[Syncthing](https://syncthing.net/) is the recommended option — free, open source, and runs on Windows, Linux, and most NAS platforms. See the [Getting Started guide](https://docs.syncthing.net/intro/getting-started.html) for setup.

Alternatives:
- **Network share (SMB):** Map your server's clips folder as a network drive on your gaming PC, then change the NVIDIA save path in GeForce Experience → **Settings** → **General** → video save location. No sync tool needed.
- **Same machine:** If you run Docker on your gaming PC, point `CLIPS_DIR` at your NVIDIA clips folder directly

---

### Step 3 — Configure

```bash
cp config.yaml.example config.yaml
cp .env.example .env
```

**`.env`** — set your clips path and Plex URL:

```bash
CLIPS_DIR=/clips               # always /clips when using the default compose file
PLEX_URL=http://192.168.1.100:32400
```

> `CLIPS_DIR` is the path *inside the container*, always `/clips` with the default compose file. Common host-side paths: Synology `/volume1/clips`, Unraid `/mnt/user/clips`, bare Linux `/mnt/clips`. Only the left side of the volume mount changes — the right side stays `/clips`.

**`config.yaml`** — enable Plex and set the library name:

```yaml
plex:
  enabled: true
  library_name: "Gaming Clips"   # must match exactly what you created in Step 1
  auto_scan: true
  auto_create_collections: true
```

> `data_dir` defaults to `data/`, which maps to `/app/data` in the container — leave it as-is. It holds the SQLite state database, Plex token, and YouTube token.

See [config.yaml.example](config.yaml.example) for all options with inline documentation.

---

### Step 4 — Authorize Plex

Get your Plex token before starting the container. This uses the [Plex PIN auth flow](https://forums.plex.tv/t/authenticating-with-plex/609370) — it contacts plex.tv directly, so your local Plex server doesn't need to be reachable, and you don't need docker-compose set up yet.

Run it as a one-off container, mounting only the data folder where the token will be saved:

```bash
docker run --rm -it \
  -v /mnt/appdata/replaytagger:/app/data \
  ghcr.io/iamclements/replay-tagger:latest \
  replaytagger plex-auth
```

Replace `/mnt/appdata/replaytagger` with your data directory — create it first if it doesn't exist (`mkdir -p /mnt/appdata/replaytagger`). The token is written to `plex_token` in that directory automatically.

```
Open this URL in your browser to authorize:

  https://app.plex.tv/auth#?clientID=...&code=XXXX

Waiting for authorization ...
Authorization successful!
Token saved to /app/data/plex_token
```

Inside the container the token is at `/app/data/plex_token`; on the host that's `<your-data-dir>/plex_token`. ReplayTagger loads it on startup — no env var needed.

**Alternative:** Set `PLEX_TOKEN=your_token` in `.env` instead. The env var takes priority over the token file.

---

### Step 5 — Set up volumes and start

Edit the left side of each volume in `docker-compose.yml` to match your host paths:

```yaml
volumes:
  - /mnt/clips:/clips                          # host clips dir → /clips in container
  - /mnt/appdata/replaytagger:/app/data        # same data dir from Step 4
  - /mnt/appdata/replaytagger/config.yaml:/app/config.yaml:ro
```

> The volume and `CLIPS_DIR` are independent: the volume exposes the host path to Docker; `CLIPS_DIR` tells ReplayTagger where to look inside the container. With the default compose file `CLIPS_DIR` is always `/clips` — only the left side of the mount changes.

```bash
docker compose up -d
docker compose logs -f
```

ReplayTagger scans all existing clips first, tags any that haven't been tagged yet, then switches to watching for new files.

---

### Step 6 — (Optional) Set up YouTube archiving

Free permanent archival storage. ReplayTagger uploads the source file without pre-encoding; YouTube re-encodes all uploads through their own pipeline regardless, so the stored copy reflects their transcoding — same as any other YouTube upload.

#### Google Cloud setup

1. [console.cloud.google.com](https://console.cloud.google.com/) → new project
2. **APIs & Services → Library** → enable **YouTube Data API v3**
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - If prompted to configure a consent screen: External → app name + email → save
4. Application type: **TV and Limited Input devices** — required for headless device flow
5. Add to `.env`:
   ```bash
   YOUTUBE_CLIENT_ID=your_client_id
   YOUTUBE_CLIENT_SECRET=your_client_secret
   ```

#### Authorize

```bash
# The first "replaytagger" is the Docker service name; the second is the CLI command
docker compose run --rm replaytagger replaytagger --config /app/config.yaml youtube-auth
```

Enter the displayed code at `google.com/device`. Token saved to `data/youtube_token.json` — one-time setup.

#### Enable in config.yaml

```yaml
youtube:
  enabled: true
  auto_upload: false        # set true to upload automatically as clips arrive
  privacy: private          # private | unlisted | public
  upload_after_days: 0      # wait N days before auto-uploading (0 = immediately)
```

> Set `upload_after_days` to a non-zero value if you want a review window before clips go public. `youtube-sync` bypasses this — use it to push a backlog on demand.

#### Upload options

| Goal | Command |
|------|---------|
| Upload a single clip now | `replaytagger upload "path/to/clip.mp4"` |
| Upload all tagged clips in batch | `replaytagger youtube-sync` |
| Auto-upload as clips arrive | Set `auto_upload: true` in config.yaml |

---

## Troubleshooting

**Clips aren't being tagged**
```bash
docker compose logs -f replaytagger
```
Check that `CLIPS_DIR` in `.env` matches the left side of the `/clips` volume in `docker-compose.yml`, and that the clips folder exists on your server.

**Plex collections aren't appearing**
Confirm the `library_name` in `config.yaml` matches your Plex library name exactly (case-sensitive). Also verify "Automatically create collections by genre" is enabled in the library's Advanced settings.

**Plex auth fails or token is rejected**
Re-run `plex-auth` to generate a fresh token — Plex tokens don't expire but can be revoked from your Plex account dashboard.

**Plex scans not triggering / collections not updating**
ReplayTagger still tags files and updates the database if Plex is unreachable — it logs a warning and continues. Check that `PLEX_URL` resolves from inside the container's network (use the LAN IP, not a hostname that only resolves on the host).

---

## Plex Collections

![Plex game collections](docs/images/plex-collections.png)

With **"Automatically create collections by genre"** enabled (Step 1), Plex handles everything — a new collection appears the first time a clip is tagged for that game.

To create collections manually instead:

1. Open your Plex library → **Collections** → **Create Smart Collection**
2. Rule: **Genre** → **is** → `Apex Legends`

---

## Configuration reference

### config.yaml

```yaml
clips_dir: /clips                    # set via CLIPS_DIR env var for Docker
extensions: [.mp4, .mkv, .mov]
data_dir: data                       # relative to working dir; /app/data in Docker

plex:
  enabled: true
  url: http://192.168.1.100:32400    # set via PLEX_URL env var
  library_name: "Gaming Clips"
  auto_scan: true
  auto_create_collections: true

youtube:
  enabled: false
  auto_upload: false
  privacy: private
  upload_after_days: 0
```

### Environment variables

Secrets always go in `.env`, never in `config.yaml`:

| Variable | Description |
|----------|-------------|
| `CLIPS_DIR` | Path to the clips folder on your server |
| `PLEX_URL` | Your Plex server URL |
| `PLEX_TOKEN` | Plex token (alternative to running `plex-auth`) |
| `YOUTUBE_CLIENT_ID` | GCP OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | GCP OAuth client secret |
| `YOUTUBE_ENABLED` | `true` or `false` — override config.yaml |
| `YOUTUBE_PRIVACY` | `private`, `unlisted`, or `public` |
| `YOUTUBE_UPLOAD_AFTER_DAYS` | Override `upload_after_days` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |
| `LOG_FORMAT` | `json` or `pretty` (default: `json`) |

---

## CLI Reference

> **Docker users:** most day-to-day operation is handled automatically. The commands below are for one-off tasks or if you're running ReplayTagger outside Docker.

```
replaytagger [--config PATH] [--dry-run] COMMAND

Commands:
  run            Scan all clips once, tag untagged files, then exit
  watch          Watch for new clips and process them as they arrive
  plex-auth      Authorize Plex via PIN flow — saves token to data/plex_token
  youtube-auth   Authorize YouTube via device flow (URL + code, no browser needed)
  youtube-sync   Upload all tagged clips that have passed upload_after_days
  upload FILE    Upload a single clip to YouTube
  status         Show tagging and upload counts from the state database
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

## NAS / Container Management UIs

Tools like Synology Container Manager, Unraid, TrueNAS SCALE, and similar UIs can deploy this container without the CLI. Use these mappings:

| Setting | Value |
|---------|-------|
| Image | `ghcr.io/iamclements/replay-tagger:latest` |
| Volume | `/your/clips/folder` → `/clips` |
| Volume | `/your/data/folder` → `/app/data` |
| Volume | `/your/config.yaml` → `/app/config.yaml` (read-only) |
| Env | `PLEX_URL`, `CLIPS_DIR`, and any others from `.env.example` |

To run auth commands on a deployed container, use your UI's console/exec feature or:

```bash
docker exec -it replaytagger replaytagger --config /app/config.yaml plex-auth
```

Pre-built images for `amd64` and `arm64` are published to GitHub Container Registry on every release. The `arm64` image runs natively on Raspberry Pi and most NAS SoCs.

---

## Development

```bash
git clone https://github.com/iamclements/replay-tagger
cd replay-tagger
make install       # creates .venv and installs package + dev deps
source .venv/bin/activate
make test          # pytest
make lint          # ruff + mypy
make docker-build  # build image locally
```

See the [Makefile](Makefile) for all available targets.

### Project Structure

```
replaytagger/
├── cli.py            # Click CLI entry point
├── config.py         # YAML + env var config loading
├── db.py             # SQLite state tracking
├── tagger.py         # ffmpeg/ffprobe genre tagging
├── plex_client.py    # Plex API integration
├── youtube_client.py # YouTube Data API v3 upload
├── watcher.py        # Watchdog file system monitor
└── logging.py        # structlog configuration
```

---

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Use the provided issue templates for [bug reports](.github/ISSUE_TEMPLATE/bug_report.md) and [feature requests](.github/ISSUE_TEMPLATE/feature_request.md).

---

## License

MIT — see [LICENSE](LICENSE).
