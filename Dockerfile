# syntax=docker/dockerfile:1

# ── Build stage: install Python dependencies into an isolated prefix ──────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE config.yaml.example ./
COPY replaytagger/ replaytagger/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install .


# ── Runtime stage: minimal image with ffmpeg ──────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="ReplayTagger" \
      org.opencontainers.image.description="Auto-tag game clips for Plex and Jellyfin collections" \
      org.opencontainers.image.source="https://github.com/iamclements/replay-tagger" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade pip

WORKDIR /app

COPY --from=builder /install /usr/local

# Create non-root user; entrypoint will remap UID/GID at runtime via PUID/PGID
RUN useradd --create-home --uid 1000 replaytagger \
    && mkdir -p /clips /app/data \
    && chown -R replaytagger:replaytagger /app /clips

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# /clips  — mount your game clips directory here
# /app/data — SQLite state DB and YouTube token persist here
VOLUME ["/clips", "/app/data"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD replaytagger --config /app/config.yaml health

ENTRYPOINT ["/entrypoint.sh", "replaytagger", "--config", "/app/config.yaml"]
CMD ["watch"]
