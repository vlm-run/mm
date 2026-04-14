#!/bin/sh
# Install mm — high-performance multimodal context management CLI
#
# Usage:
#   curl -LsSf https://vlm-run.github.io/mm/install/install.sh | sh
#
# Options (via env vars):
#   MM_VERSION=0.4.0       Install a specific version (default: latest published)
#   MM_FROM_GIT=1          Build from source (requires SSH + Rust toolchain)
#   MM_GIT_REF=v0.4.0     Git ref to build from (default: latest, requires MM_FROM_GIT=1)
#   MM_NO_MODIFY_PATH=1   Skip PATH modification
#   MM_SKIP_VERIFY=1       Skip checksum verification (not recommended)

set -eu

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

BASE_URL="https://vlm-run.github.io/mm/install"

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
    ARCH="$(uname -m)"

    case "$OS" in
        Linux)          PLATFORM_OS="linux" ;;
        Darwin)         PLATFORM_OS="macos" ;;
        MINGW*|MSYS*|CYGWIN*)
            err "detected Windows shell (${OS}). Use the PowerShell installer instead:
  irm https://vlm-run.github.io/mm/install/install.ps1 | iex" ;;
        *)              err "unsupported OS: ${OS}. mm supports Linux, macOS, and Windows." ;;
    esac

    case "$ARCH" in
        x86_64|amd64)   PLATFORM_ARCH="x86_64" ;;
        aarch64|arm64)  PLATFORM_ARCH="aarch64" ;;
        *)              err "unsupported architecture: ${ARCH}. mm supports x86_64 and aarch64." ;;
    esac

    # Wheel filename patterns differ from uname output:
    #   linux x86_64   → manylinux*x86_64
    #   linux aarch64  → manylinux*aarch64
    #   macos x86_64   → macosx*x86_64
    #   macos aarch64  → macosx*arm64
    case "${PLATFORM_OS}-${PLATFORM_ARCH}" in
        linux-x86_64)   WHEEL_PATTERN="manylinux.*x86_64" ;;
        linux-aarch64)  WHEEL_PATTERN="manylinux.*aarch64" ;;
        macos-x86_64)   WHEEL_PATTERN="macosx.*x86_64" ;;
        macos-aarch64)  WHEEL_PATTERN="macosx.*arm64" ;;
    esac

    PLATFORM="${PLATFORM_OS}-${PLATFORM_ARCH}"
    info "detected platform: ${PLATFORM}"
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

# ── Ensure Rust (source builds only) ─────────────────────────────

ensure_rust() {
    if command -v rustc > /dev/null 2>&1; then
        info "found rust: $(rustc --version)"
        return
    fi

    info "rust not found — installing via rustup..."
    need_cmd curl
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

    if [ -f "$HOME/.cargo/env" ]; then
        . "$HOME/.cargo/env"
    fi

    if ! command -v rustc > /dev/null 2>&1; then
        err "rust installation succeeded but 'rustc' not found in PATH"
    fi

    info "installed rust: $(rustc --version)"
}

# ── Checksum verification ─────────────────────────────────────────

verify_checksum() {
    FILE="$1"
    EXPECTED="$2"

    if command -v sha256sum > /dev/null 2>&1; then
        ACTUAL="$(sha256sum "$FILE" | cut -d' ' -f1)"
    elif command -v shasum > /dev/null 2>&1; then
        ACTUAL="$(shasum -a 256 "$FILE" | cut -d' ' -f1)"
    else
        warn "neither sha256sum nor shasum found — skipping checksum verification"
        return 0
    fi

    if [ "$ACTUAL" = "$EXPECTED" ]; then
        info "checksum verified: ${ACTUAL}"
        return 0
    else
        printf "\n"
        printf "${BOLD}${RED}  CHECKSUM MISMATCH${RESET}\n"
        printf "  expected: ${CYAN}%s${RESET}\n" "$EXPECTED"
        printf "  actual:   ${CYAN}%s${RESET}\n" "$ACTUAL"
        printf "\n"
        err "checksum verification failed — the download may be corrupted or tampered with"
    fi
}

# ── Download & verify wheel ───────────────────────────────────────

download_wheel() {
    need_cmd curl

    VERSION="${MM_VERSION:-latest}"
    MANIFEST_URL="${BASE_URL}/${VERSION}/SHA256SUMS"
    TMPDIR="$(mktemp -d)"
    trap 'rm -rf "$TMPDIR"' EXIT

    info "fetching manifest for version: ${VERSION}..."
    if ! curl -fsSL "$MANIFEST_URL" -o "${TMPDIR}/SHA256SUMS" 2>/dev/null; then
        if [ "$VERSION" = "latest" ]; then
            err "could not fetch manifest from ${MANIFEST_URL}
No pre-built wheels found. Install from source with:
  curl -LsSf ${BASE_URL}/install.sh | MM_FROM_GIT=1 sh"
        else
            err "version ${VERSION} not found at ${MANIFEST_URL}"
        fi
    fi

    # Find the wheel for this platform using wheel filename conventions
    WHEEL_NAME="$(grep -E "${WHEEL_PATTERN}" "${TMPDIR}/SHA256SUMS" | head -1 | awk '{print $2}')"
    if [ -z "$WHEEL_NAME" ]; then
        err "no pre-built wheel for ${PLATFORM} in version ${VERSION}
Install from source with:
  curl -LsSf ${BASE_URL}/install.sh | MM_FROM_GIT=1 sh"
    fi

    EXPECTED_HASH="$(grep "${WHEEL_NAME}" "${TMPDIR}/SHA256SUMS" | head -1 | awk '{print $1}')"
    WHEEL_URL="${BASE_URL}/${VERSION}/${WHEEL_NAME}"

    info "downloading ${WHEEL_NAME}..."
    curl -fsSL "$WHEEL_URL" -o "${TMPDIR}/${WHEEL_NAME}"

    # Verify checksum
    if [ "${MM_SKIP_VERIFY:-0}" != "1" ]; then
        verify_checksum "${TMPDIR}/${WHEEL_NAME}" "$EXPECTED_HASH"
    else
        warn "checksum verification skipped (MM_SKIP_VERIFY=1)"
    fi

    WHEEL_PATH="${TMPDIR}/${WHEEL_NAME}"
    info "wheel ready: ${WHEEL_NAME}"
}

# ── Install mm ────────────────────────────────────────────────────

install_mm() {
    FROM_GIT="${MM_FROM_GIT:-0}"

    if [ "$FROM_GIT" = "1" ]; then
        # Source build path
        ensure_rust

        GIT_REF="${MM_GIT_REF:-}"
        REPO="git+ssh://git@github.com/vlm-run/mm.git"

        if [ -n "$GIT_REF" ]; then
            SOURCE="${REPO}@${GIT_REF}"
            info "installing mm from source (${GIT_REF})..."
        else
            SOURCE="${REPO}"
            info "installing mm from source (latest)..."
        fi

        if uv tool install mm --from "$SOURCE" --force 2>&1; then
            info "mm installed successfully (from source)"
        else
            err "failed to install mm — do you have SSH access to github.com/vlm-run/mm?"
        fi
    else
        # Pre-built wheel path
        download_wheel

        if uv tool install mm --from "$WHEEL_PATH" --force 2>&1; then
            info "mm installed successfully"
        else
            err "failed to install mm from wheel"
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
    printf "${BOLD}  mm installer${RESET}\n"
    printf "  high-performance multimodal context management\n"
    printf "\n"

    detect_platform
    ensure_uv
    install_mm
    verify_install

    printf "\n"
    info "Get started:"
    info "  mm --help"
    info "  mm find . --tree"
    printf "\n"
}

main
