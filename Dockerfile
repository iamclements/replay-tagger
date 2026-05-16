# syntax=docker/dockerfile:1

# ── Build stage: install Python dependencies into an isolated prefix ──────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY replaytagger/ replaytagger/

RUN pip install --no-cache-dir --prefix=/install .


# ── Runtime stage: minimal image with ffmpeg ──────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="ReplayTagger" \
      org.opencontainers.image.description="Auto-tag NVIDIA game clips for Plex collections" \
      org.opencontainers.image.source="https://github.com/iamclements/replay-tagger" \
      org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local

# Non-root user for security
RUN useradd --create-home --uid 1000 replaytagger \
    && mkdir -p /clips /app/data \
    && chown -R replaytagger:replaytagger /app /clips

USER replaytagger

# /clips  — mount your game clips directory here
# /app/data — SQLite state DB and YouTube token persist here
VOLUME ["/clips", "/app/data"]

HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import replaytagger; print('ok')" || exit 1

ENTRYPOINT ["replaytagger", "--config", "/app/config.yaml"]
CMD ["watch"]
