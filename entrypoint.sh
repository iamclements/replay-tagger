#!/bin/bash
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

groupmod -o -g "$PGID" replaytagger
usermod -o -u "$PUID" replaytagger

chown -R replaytagger:replaytagger /app

exec gosu replaytagger "$@"
