#!/bin/bash
# Build the server-mode image (docker/Dockerfile, docs/server.md) from a
# build: tools/build.sh, then this. Anki's core on the server is the PyPI
# release named in the Kioku repo's shared/versions.env, the version the
# app is built from, so an Anki update needs nothing here.
# Usage: docker.sh [image tag] [extra docker build args...]
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$KIOKU_REPO/shared/versions.env"
TAG=${1:-kioku-server}
shift || true
"$ROOT/tools/dist.sh" >/dev/null
docker build -f "$ROOT/docker/Dockerfile" --build-arg "ANKI_PY_VERSION=$ANKI_PY_VERSION" -t "$TAG" "$@" "$ROOT"
