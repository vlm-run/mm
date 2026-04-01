#!/bin/sh
# Install mm — high-performance multi-modal context management CLI
# Usage: curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
# Or:    curl -LsSf https://vlm.run/mm/install.sh | sh  (with redirect from vlm.run)
#
# Options (via env vars):
#   MM_VERSION=0.1.2       Install a specific version (default: latest)
#   MM_NO_MODIFY_PATH=1    Skip PATH modification

set -eu

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info() {
    printf "${BOLD}${GREEN}info${RESET}: %s\n" "$1"
}

warn() {
    printf "${BOLD}${YELLOW}warn${RESET}: %s\n" "$1"
}

err() {
    printf "${BOLD}${RED}error${RESET}: %s\n" "$1" >&2
    exit 1
}

# --- Pre-flight checks ---

# Need curl or wget for potential uv install
need_cmd() {
    if ! command -v "$1" > /dev/null 2>&1; then
        err "need '$1' (command not found)"
    fi
}

# --- Detect platform ---

detect_platform() {
    OS="$(uname -s)"
    ARCH="$(uname -m)"

    case "$OS" in
        Linux)  OS="linux" ;;
        Darwin) OS="macos" ;;
        *)      err "unsupported OS: $OS" ;;
    esac

    case "$ARCH" in
        x86_64|amd64)   ARCH="x86_64" ;;
        aarch64|arm64)   ARCH="aarch64" ;;
        *)               err "unsupported architecture: $ARCH" ;;
    esac

    info "detected platform: ${OS}-${ARCH}"
}

# --- Ensure uv is available ---

ensure_uv() {
    if command -v uv > /dev/null 2>&1; then
        info "found uv: $(uv --version)"
        return
    fi

    info "uv not found — installing uv first..."
    need_cmd curl
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source uv's env so it's available in this session
    if [ -f "$HOME/.local/bin/env" ]; then
        . "$HOME/.local/bin/env"
    elif [ -f "$HOME/.cargo/env" ]; then
        . "$HOME/.cargo/env"
    fi

    # Add to PATH as fallback
    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v uv > /dev/null 2>&1; then
        err "uv installation succeeded but 'uv' not found in PATH"
    fi

    info "installed uv: $(uv --version)"
}

# --- Install mm ---

install_mm() {
    VERSION="${MM_VERSION:-}"

    if [ -n "$VERSION" ]; then
        PACKAGE="mm==${VERSION}"
        info "installing mm ${VERSION}..."
    else
        PACKAGE="mm"
        info "installing mm (latest)..."
    fi

    # uv tool install puts the binary in ~/.local/bin
    if uv tool install "$PACKAGE" --force 2>&1; then
        info "mm installed successfully"
    else
        err "failed to install mm"
    fi
}

# --- Verify installation ---

verify() {
    # Ensure ~/.local/bin is in PATH for verification
    export PATH="$HOME/.local/bin:$PATH"

    if command -v mm > /dev/null 2>&1; then
        info "mm is ready: $(mm --version 2>/dev/null || echo 'installed')"
        MM_BIN="$(command -v mm)"
        info "binary location: ${MM_BIN}"
    else
        warn "mm was installed but is not in your PATH"
        warn "add this to your shell profile:"
        echo ""
        echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
        echo ""
    fi
}

# --- Main ---

main() {
    printf "\n"
    printf "${BOLD}  mm installer${RESET}\n"
    printf "  high-performance multi-modal context management\n"
    printf "\n"

    detect_platform
    ensure_uv
    install_mm
    verify

    printf "\n"
    info "get started: mm find . --tree"
    printf "\n"
}

main
