# Sourced by the tools: paths to this repository and to the Kioku repository
# (github.com/krmanik/kioku), which provides Anki's source and Rust core
# (ios/deps/anki), the shared kioku Python package (shared/python), the
# PyQt6 sdists and sip-build (ios/deps/sdist, ios/.venv) and host Qt
# (ios/deps/qt/6.11.0/macos). Set KIOKU_REPO if it isn't a sibling folder.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
KIOKU_REPO=${KIOKU_REPO:-$ROOT/../anki-desktop-for-android}
KIOKU_REPO=$(cd "$KIOKU_REPO" && pwd)
