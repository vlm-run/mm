#!/bin/sh
# Install mm — high-performance multimodal context management CLI
#
# Usage:
#   curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
#
# Options (via env vars):
#   MM_VERSION=0.5.1       Install a specific version (default: latest)
#   MM_NO_MODIFY_PATH=1   Skip PATH modification

set -eu

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()  { printf "${BOLD}${GREEN}info${RESET}: %s\n" "$1"; }
warn()  { printf "${BOLD}${YELLOW}warn${RESET}: %s\n" "$1"; }
err()   { printf "${BOLD}${RED}error${RESET}: %s\n" "$1" >&2; exit 1; }

# ── Pre-flight ────────────────────────────────────────────────────

need_cmd() {
    if ! command -v "$1" > /dev/null 2>&1; then
        err "need '$1' (command not found)"
    fi
}

# ── Platform detection ────────────────────────────────────────────

detect_platform() {
    OS="$(uname -s)"

    case "$OS" in
        Linux|Darwin)   ;;
        MINGW*|MSYS*|CYGWIN*)
            err "detected Windows shell (${OS}). Use the PowerShell installer instead:
  irm https://vlm-run.github.io/mm/install/install.ps1 | iex" ;;
        *)              err "unsupported OS: ${OS}. mm supports Linux, macOS, and Windows." ;;
    esac

    info "detected platform: ${OS} $(uname -m)"
}

# ── Ensure uv ─────────────────────────────────────────────────────

ensure_uv() {
    if command -v uv > /dev/null 2>&1; then
        info "found uv: $(uv --version)"
        return
    fi

    info "uv not found — installing uv first..."
    need_cmd curl
    curl -LsSf https://astral.sh/uv/install.sh | sh

    if [ -f "$HOME/.local/bin/env" ]; then
        . "$HOME/.local/bin/env"
    elif [ -f "$HOME/.cargo/env" ]; then
        . "$HOME/.cargo/env"
    fi

    if [ "${MM_NO_MODIFY_PATH:-0}" = "0" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if ! command -v uv > /dev/null 2>&1; then
        err "uv installation succeeded but 'uv' not found in PATH"
    fi

    info "installed uv: $(uv --version)"
}

# ── Install mm from PyPI ─────────────────────────────────────────

install_mm() {
    VERSION="${MM_VERSION:-}"

    if [ -n "$VERSION" ]; then
        info "installing mm-ctx==${VERSION} from PyPI..."
        if uv tool install "mm-ctx==${VERSION}" --force 2>&1; then
            info "mm installed successfully (v${VERSION})"
        else
            err "failed to install mm-ctx==${VERSION} from PyPI"
        fi
    else
        info "installing mm-ctx from PyPI (latest)..."
        if uv tool install mm-ctx --force 2>&1; then
            info "mm installed successfully"
        else
            err "failed to install mm-ctx from PyPI"
        fi
    fi
}

# ── Verify installation ──────────────────────────────────────────

verify_install() {
    if [ "${MM_NO_MODIFY_PATH:-0}" = "0" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if command -v mm > /dev/null 2>&1; then
        info "mm is ready: $(mm --version 2>/dev/null || echo 'installed')"
        info "binary location: $(command -v mm)"
    else
        warn "mm was installed but is not in your PATH"
        warn "add this to your shell profile:"
        echo ""
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
    fi
}

# ── Main ──────────────────────────────────────────────────────────

main() {
    printf "\n"
    printf "${BOLD}${GREEN}"
    printf "  ███╗   ███╗███╗   ███╗\n"
    printf "  ████╗ ████║████╗ ████║\n"
    printf "  ██╔████╔██║██╔████╔██║\n"
    printf "  ██║╚██╔╝██║██║╚██╔╝██║\n"
    printf "  ██║ ╚═╝ ██║██║ ╚═╝ ██║\n"
    printf "  ╚═╝     ╚═╝╚═╝     ╚═╝\n"
    printf "${RESET}\n"
    printf "  Fast, multimodal context for agents\n"
    printf "\n"

    detect_platform
    ensure_uv
    install_mm
    verify_install

    printf "\n"
    info "Get started:"
    info "mm --help"
    info "mm find . --tree"
    printf "\n"
}

main
