#!/usr/bin/env bash
# =============================================================================
# Mac EXE Runner
# Run Windows .exe files on macOS without installing Windows.
# Uses Wine (open-source Windows compatibility layer) under the hood.
# =============================================================================

set -euo pipefail

VERSION="1.1.0"
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

# --------------- Architecture Detection ---------------
is_apple_silicon() {
    [[ "$(uname -m)" == "arm64" ]]
}

# --------------- Dependency Checks ---------------
check_macos() {
    if [[ "$(uname -s)" != "Darwin" ]]; then
        error "This tool is designed for macOS. Detected: $(uname -s)"
        error "On Linux, you can install Wine directly via your package manager."
        exit 1
    fi
    local arch_info=""
    if is_apple_silicon; then
        arch_info=" (Apple Silicon)"
    else
        arch_info=" (Intel)"
    fi
    success "Running on macOS $(sw_vers -productVersion)${arch_info}"
}

check_rosetta() {
    if is_apple_silicon; then
        if /usr/bin/pgrep -q oahd 2>/dev/null || arch -x86_64 /usr/bin/true 2>/dev/null; then
            success "Rosetta 2 is installed"
            return 0
        else
            return 1
        fi
    fi
    return 0
}

install_rosetta() {
    step "Installing Rosetta 2 (required for Wine on Apple Silicon)..."
    softwareupdate --install-rosetta --agree-to-license
    if check_rosetta; then
        success "Rosetta 2 installed"
    else
        error "Rosetta 2 installation failed."
        error "Try manually: softwareupdate --install-rosetta --agree-to-license"
        exit 1
    fi
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

# Check if current Wine install supports 32-bit apps on Apple Silicon
check_wine_32bit_support() {
    local wine_cmd
    wine_cmd=$(command -v wine64 || command -v wine || echo "")
    if [[ -z "$wine_cmd" ]]; then
        return 1
    fi
    local wine_ver
    wine_ver=$($wine_cmd --version 2>/dev/null || echo "")
    # wine-crossover builds include "crossover" or are from the CrossOver source
    # They support 32-bit via wine32on64 thunking
    if echo "$wine_ver" | grep -qi "crossover"; then
        return 0
    fi
    # Check if it's a Gcenx wine-crossover build (may just say wine-X.X)
    # Look for the wine32on64 binary as a definitive check
    local wine_dir
    wine_dir="$(dirname "$wine_cmd")"
    if [[ -f "$wine_dir/wine32on64" ]]; then
        return 0
    fi
    # Check in the Wine Stable.app bundle
    if [[ -d "/Applications/Wine Crossover.app" ]]; then
        return 0
    fi
    return 1
}

install_wine() {
    if is_apple_silicon; then
        step "Installing Wine CrossOver for Apple Silicon..."
        info "This version supports both 32-bit and 64-bit Windows apps."
        info "This may take several minutes on first install."
        echo ""

        # On Apple Silicon, wine-crossover is required for 32-bit .exe support
        # First, remove wine-stable if present (it can't run 32-bit apps)
        if brew list --cask wine-stable &>/dev/null 2>&1; then
            warn "Removing wine-stable (does not support 32-bit apps on Apple Silicon)..."
            brew uninstall --cask wine-stable 2>/dev/null || true
        fi

        brew tap gcenx/wine 2>/dev/null || true
        brew install --cask --no-quarantine wine-crossover 2>/dev/null \
            || {
                error "Could not install wine-crossover automatically."
                error "Please try installing manually:"
                error "  brew tap gcenx/wine"
                error "  brew install --cask --no-quarantine wine-crossover"
                exit 1
            }
    else
        step "Installing Wine via Homebrew..."
        info "This may take several minutes on first install."
        echo ""

        # On Intel Macs, wine-stable works fine for both 32-bit and 64-bit
        brew install --cask --no-quarantine wine-stable 2>/dev/null \
            || {
                brew tap gcenx/wine 2>/dev/null || true
                brew install --cask --no-quarantine wine-crossover 2>/dev/null \
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
    fi

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
    local extra_args=()
    if [[ $# -gt 0 ]]; then
        extra_args=("$@")
    fi

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

    local args_display="none"
    if [[ ${#extra_args[@]} -gt 0 ]]; then
        args_display="${extra_args[*]}"
    fi

    step "Running: $(basename "$exe_path")"
    info "Wine command: $wine_cmd"
    info "Wine prefix: $WINE_PREFIX"
    info "Arguments: $args_display"
    echo ""

    log "Running: $exe_path with args: $args_display"

    # Run the exe through Wine
    if [[ ${#extra_args[@]} -gt 0 ]]; then
        WINEPREFIX="$WINE_PREFIX" $wine_cmd "$exe_path" "${extra_args[@]}" 2>&1 | tee -a "$LOG_FILE"
    else
        WINEPREFIX="$WINE_PREFIX" $wine_cmd "$exe_path" 2>&1 | tee -a "$LOG_FILE"
    fi
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

    # On Apple Silicon, ensure Rosetta 2 is installed
    if is_apple_silicon; then
        if ! check_rosetta; then
            install_rosetta
        fi
    fi

    if ! check_homebrew; then
        install_homebrew
    fi

    if ! check_wine; then
        install_wine
    elif is_apple_silicon && ! check_wine_32bit_support; then
        echo ""
        warn "Current Wine install does NOT support 32-bit apps on Apple Silicon."
        warn "You need wine-crossover for 32-bit .exe support."
        info "Switching to wine-crossover..."
        echo ""
        install_wine
    fi

    # Reset wine prefix when switching Wine versions
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
        if is_apple_silicon; then
            if check_wine_32bit_support; then
                success "32-bit app support: YES (wine-crossover/wine32on64)"
            else
                warn "32-bit app support: NO (need wine-crossover, run: $0 setup)"
            fi
        fi
    else
        warn "Wine is NOT installed"
    fi

    if is_apple_silicon; then
        if check_rosetta; then
            : # already printed above
        else
            warn "Rosetta 2 is NOT installed (required for Wine on Apple Silicon)"
        fi
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
            # Auto-setup if Wine isn't installed or lacks 32-bit support
            if ! check_wine 2>/dev/null; then
                warn "Wine is not installed. Running setup first..."
                echo ""
                cmd_setup
                echo ""
            elif is_apple_silicon && ! check_wine_32bit_support 2>/dev/null; then
                warn "Current Wine does not support 32-bit apps on Apple Silicon."
                warn "Running setup to install wine-crossover..."
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
                elif is_apple_silicon && ! check_wine_32bit_support 2>/dev/null; then
                    warn "Current Wine does not support 32-bit apps on Apple Silicon."
                    warn "Running setup to install wine-crossover..."
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
