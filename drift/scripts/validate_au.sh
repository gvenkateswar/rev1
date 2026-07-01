#!/usr/bin/env bash
# Build the Drift AU on macOS and validate it with auval.
# Run from the drift/ directory: ./scripts/validate_au.sh
set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "error: Audio Units and auval only exist on macOS." >&2
    exit 1
fi

cd "$(dirname "$0")/.."

cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target Drift_AU --parallel

# Install where the AU host (and auval) can find it, then force a rescan.
AU_DIR="$HOME/Library/Audio/Plug-Ins/Components"
mkdir -p "$AU_DIR"
rm -rf "$AU_DIR/Drift.component"
cp -R build/Drift_artefacts/Release/AU/Drift.component "$AU_DIR/"
killall -9 AudioComponentRegistrar 2>/dev/null || true

# Type aumu (music device), subtype Drft, manufacturer Drfa — must match
# AU_MAIN_TYPE / PLUGIN_CODE / PLUGIN_MANUFACTURER_CODE in CMakeLists.txt.
auval -strict -v aumu Drft Drfa
