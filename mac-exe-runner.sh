#!/usr/bin/env bash
# =============================================================================
# Mac EXE Runner
# Run Windows .exe files on macOS without installing Windows.
# Uses Wine (open-source Windows compatibility layer) under the hood.
# =============================================================================

set -euo pipefail

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/.exe-runner.log"
WINE_PREFIX="${WINE_PREFIX:-$HOME/.wine}"

# --------------- Colors & Formatting ---------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║         🍷  Mac EXE Runner  v${VERSION}       ║"
    echo "  ║   Run Windows .exe files on macOS        ║"
    echo "  ║   No Windows installation required       ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
success() { echo -e "${GREEN}[OK]${NC}      $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
step()    { echo -e "${BOLD}${CYAN}==>${NC} ${BOLD}$*${NC}"; }

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# --------------- Dependency Checks ---------------
check_macos() {
    if [[ "$(uname -s)" != "Darwin" ]]; then
        error "This tool is designed for macOS. Detected: $(uname -s)"
        error "On Linux, you can install Wine directly via your package manager."
        exit 1
    fi
    success "Running on macOS $(sw_vers -productVersion)"
}

check_homebrew() {
    if command -v brew &>/dev/null; then
        success "Homebrew is installed"
        return 0
    else
        return 1
    fi
}

install_homebrew() {
    step "Installing Homebrew (macOS package manager)..."
    info "This is required to install Wine. You may be prompted for your password."
    echo ""
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for Apple Silicon Macs
    if [[ -f "/opt/homebrew/bin/brew" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi

    if command -v brew &>/dev/null; then
        success "Homebrew installed successfully"
    else
        error "Homebrew installation failed. Please install manually:"
        error "  https://brew.sh"
        exit 1
    fi
}

check_wine() {
    if command -v wine &>/dev/null || command -v wine64 &>/dev/null; then
        local wine_cmd
        wine_cmd=$(command -v wine64 || command -v wine)
        local wine_ver
        wine_ver=$($wine_cmd --version 2>/dev/null || echo "unknown")
        success "Wine is installed ($wine_ver)"
        return 0
    else
        return 1
    fi
}

install_wine() {
    step "Installing Wine via Homebrew..."
    info "This may take several minutes on first install."
    echo ""

    # Tap the cask versions for wine-stable
    brew install --cask --no-quarantine wine-stable 2>/dev/null \
        || brew install --cask --no-quarantine wine-staging 2>/dev/null \
        || brew install wine-crossover 2>/dev/null \
        || {
            warn "Standard Wine install failed, trying alternative tap..."
            brew tap gcenx/wine 2>/dev/null || true
            brew install --cask --no-quarantine gcenx-wine-stable 2>/dev/null \
                || brew install --cask --no-quarantine wine-crossover 2>/dev/null \
                || {
                    error "Could not install Wine automatically."
                    error "Please try installing manually:"
                    error "  brew tap gcenx/wine"
                    error "  brew install --cask --no-quarantine wine-crossover"
                    error ""
                    error "Or visit: https://wiki.winehq.org/Download"
                    exit 1
                }
        }

    if check_wine; then
        success "Wine installed successfully!"
    else
        error "Wine was installed but could not be found on PATH."
        error "Try restarting your terminal and running this script again."
        exit 1
    fi
}

get_wine_cmd() {
    if command -v wine64 &>/dev/null; then
        echo "wine64"
    elif command -v wine &>/dev/null; then
        echo "wine"
    else
        error "Wine not found on PATH"
        exit 1
    fi
}

# --------------- Wine Prefix Management ---------------
init_wine_prefix() {
    local wine_cmd
    wine_cmd=$(get_wine_cmd)

    if [[ ! -d "$WINE_PREFIX/drive_c" ]]; then
        step "Initializing Wine prefix at $WINE_PREFIX..."
        info "This sets up a virtual Windows environment (one-time setup)."
        WINEPREFIX="$WINE_PREFIX" $wine_cmd wineboot --init 2>/dev/null || true
        success "Wine prefix initialized"
    fi
}

# --------------- EXE Runner ---------------
run_exe() {
    local exe_path="$1"
    shift
    local extra_args=("$@")

    # Resolve to absolute path
    if [[ ! "$exe_path" = /* ]]; then
        exe_path="$(pwd)/$exe_path"
    fi

    if [[ ! -f "$exe_path" ]]; then
        error "File not found: $exe_path"
        exit 1
    fi

    if [[ "${exe_path##*.}" != "exe" && "${exe_path##*.}" != "EXE" ]]; then
        warn "File does not have .exe extension: $exe_path"
        read -rp "Run anyway? [y/N]: " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            info "Aborted."
            exit 0
        fi
    fi

    local wine_cmd
    wine_cmd=$(get_wine_cmd)

    step "Running: $(basename "$exe_path")"
    info "Wine command: $wine_cmd"
    info "Wine prefix: $WINE_PREFIX"
    info "Arguments: ${extra_args[*]:-none}"
    echo ""

    log "Running: $exe_path with args: ${extra_args[*]:-none}"

    # Run the exe through Wine
    WINEPREFIX="$WINE_PREFIX" $wine_cmd "$exe_path" "${extra_args[@]}" 2>&1 | tee -a "$LOG_FILE"
    local exit_code=${PIPESTATUS[0]}

    echo ""
    if [[ $exit_code -eq 0 ]]; then
        success "Program exited normally (code 0)"
    else
        warn "Program exited with code $exit_code"
    fi

    log "Exit code: $exit_code"
    return $exit_code
}

# --------------- Utility Commands ---------------
cmd_setup() {
    print_banner
    step "Setting up Mac EXE Runner..."
    echo ""

    check_macos

    if ! check_homebrew; then
        install_homebrew
    fi

    if ! check_wine; then
        install_wine
    fi

    init_wine_prefix

    echo ""
    success "Setup complete! You can now run .exe files with:"
    echo ""
    echo -e "    ${BOLD}./mac-exe-runner.sh run <file.exe>${NC}"
    echo ""
}

cmd_status() {
    print_banner
    step "Checking system status..."
    echo ""

    echo -e "${BOLD}System:${NC}"
    if [[ "$(uname -s)" == "Darwin" ]]; then
        success "macOS $(sw_vers -productVersion) ($(uname -m))"
    else
        warn "Not macOS: $(uname -s)"
    fi

    echo ""
    echo -e "${BOLD}Dependencies:${NC}"

    if check_homebrew; then
        info "  Location: $(which brew)"
    else
        warn "Homebrew is NOT installed"
    fi

    if check_wine; then
        info "  Location: $(which wine64 2>/dev/null || which wine)"
    else
        warn "Wine is NOT installed"
    fi

    echo ""
    echo -e "${BOLD}Wine Prefix:${NC}"
    if [[ -d "$WINE_PREFIX/drive_c" ]]; then
        success "Initialized at $WINE_PREFIX"
        info "  Virtual C:\\ drive: $WINE_PREFIX/drive_c"
        local size
        size=$(du -sh "$WINE_PREFIX" 2>/dev/null | cut -f1)
        info "  Prefix size: $size"
    else
        warn "Not initialized (will be created on first run)"
    fi

    echo ""
}

cmd_config() {
    local wine_cmd
    wine_cmd=$(get_wine_cmd)

    case "${1:-}" in
        winecfg)
            step "Opening Wine Configuration..."
            WINEPREFIX="$WINE_PREFIX" $wine_cmd winecfg &
            ;;
        regedit)
            step "Opening Wine Registry Editor..."
            WINEPREFIX="$WINE_PREFIX" $wine_cmd regedit &
            ;;
        taskmgr)
            step "Opening Wine Task Manager..."
            WINEPREFIX="$WINE_PREFIX" $wine_cmd taskmgr &
            ;;
        explorer)
            step "Opening Wine Explorer..."
            WINEPREFIX="$WINE_PREFIX" $wine_cmd explorer &
            ;;
        *)
            info "Available config tools:"
            echo "  winecfg   - Wine configuration (set Windows version, etc.)"
            echo "  regedit   - Windows registry editor"
            echo "  taskmgr   - Task manager (see running processes)"
            echo "  explorer  - File explorer"
            echo ""
            echo "Usage: $0 config <tool>"
            ;;
    esac
}

cmd_kill() {
    step "Stopping all Wine processes..."
    WINEPREFIX="$WINE_PREFIX" wineserver -k 2>/dev/null || true
    success "All Wine processes terminated"
}

cmd_reset() {
    warn "This will delete your Wine prefix at: $WINE_PREFIX"
    warn "All installed Windows programs and settings will be lost."
    read -rp "Are you sure? [y/N]: " confirm
    if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
        WINEPREFIX="$WINE_PREFIX" wineserver -k 2>/dev/null || true
        rm -rf "$WINE_PREFIX"
        success "Wine prefix deleted. Run 'setup' to reinitialize."
    else
        info "Aborted."
    fi
}

# --------------- Usage ---------------
usage() {
    print_banner
    echo -e "${BOLD}USAGE:${NC}"
    echo "  $0 <command> [options]"
    echo ""
    echo -e "${BOLD}COMMANDS:${NC}"
    echo "  run <file.exe> [args...]   Run a Windows .exe file"
    echo "  setup                      Install dependencies (Homebrew + Wine)"
    echo "  status                     Check if everything is installed"
    echo "  config [tool]              Open Wine config tools (winecfg, regedit, etc.)"
    echo "  kill                       Stop all running Wine processes"
    echo "  reset                      Delete Wine prefix and start fresh"
    echo "  help                       Show this help message"
    echo ""
    echo -e "${BOLD}EXAMPLES:${NC}"
    echo "  $0 setup                          # First-time setup"
    echo "  $0 run MyApp.exe                  # Run an exe file"
    echo "  $0 run installer.exe /S           # Run with arguments"
    echo "  $0 run ~/Downloads/game.exe       # Run from any path"
    echo "  $0 config winecfg                 # Change Windows version"
    echo ""
    echo -e "${BOLD}ENVIRONMENT:${NC}"
    echo "  WINE_PREFIX   Custom Wine prefix path (default: ~/.wine)"
    echo ""
    echo -e "${BOLD}HOW IT WORKS:${NC}"
    echo "  This tool uses Wine, an open-source compatibility layer that translates"
    echo "  Windows API calls into macOS equivalents in real-time. No Windows license"
    echo "  or installation is needed. Most Windows applications work out of the box."
    echo ""
    echo "  Learn more: https://www.winehq.org"
    echo ""
}

# --------------- Main ---------------
main() {
    local command="${1:-help}"

    case "$command" in
        run)
            if [[ $# -lt 2 ]]; then
                error "Missing .exe file path"
                echo "Usage: $0 run <file.exe> [args...]"
                exit 1
            fi
            # Auto-setup if Wine isn't installed
            if ! check_wine 2>/dev/null; then
                warn "Wine is not installed. Running setup first..."
                echo ""
                cmd_setup
                echo ""
            fi
            init_wine_prefix
            shift
            run_exe "$@"
            ;;
        setup)
            cmd_setup
            ;;
        status)
            cmd_status
            ;;
        config)
            shift
            cmd_config "${1:-}"
            ;;
        kill)
            cmd_kill
            ;;
        reset)
            cmd_reset
            ;;
        help|--help|-h)
            usage
            ;;
        --version|-v)
            echo "Mac EXE Runner v${VERSION}"
            ;;
        *)
            # If it looks like an .exe path, just run it directly
            if [[ "$command" == *.exe || "$command" == *.EXE ]]; then
                if ! check_wine 2>/dev/null; then
                    warn "Wine is not installed. Running setup first..."
                    echo ""
                    cmd_setup
                    echo ""
                fi
                init_wine_prefix
                run_exe "$@"
            else
                error "Unknown command: $command"
                echo "Run '$0 help' for usage information."
                exit 1
            fi
            ;;
    esac
}

main "$@"
