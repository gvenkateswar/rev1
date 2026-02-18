#!/usr/bin/env bash
# =============================================================================
# Quick Setup - Mac EXE Runner
# One-command installer: just run ./setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  Mac EXE Runner - Quick Setup"
echo "  ============================="
echo ""

# Make the main script executable
chmod +x "$SCRIPT_DIR/mac-exe-runner.sh"

# Run setup
exec "$SCRIPT_DIR/mac-exe-runner.sh" setup
