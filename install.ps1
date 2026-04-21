# Install mm — Fast, multimodal file intelligence for agents
#
# Usage:
#   irm https://vlm-run.github.io/mm/install/install.ps1 | iex
#
# Options (via env vars):
#   $env:MM_VERSION = "0.5.1"    Install a specific version (default: latest)

$ErrorActionPreference = "Stop"

function Write-Info  { param($Msg) Write-Host "info: $Msg" -ForegroundColor Green }
function Write-Warn  { param($Msg) Write-Host "warn: $Msg" -ForegroundColor Yellow }
function Write-Err   { param($Msg) Write-Host "error: $Msg" -ForegroundColor Red; throw $Msg }

# ── Platform detection ───────────────────────────────────────────

function Get-Platform {
    $arch = $env:PROCESSOR_ARCHITECTURE
    if (-not $arch) {
        try {
            $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        } catch { $arch = "unknown" }
    }
    Write-Info "detected platform: Windows $arch"
}

# ── Ensure uv ────────────────────────────────────────────────────

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Info "found uv: $(uv --version)"
        return
    }

    Write-Info "uv not found — installing uv first..."
    irm https://astral.sh/uv/install.ps1 | iex

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")

    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Err "uv installation succeeded but 'uv' not found in PATH"
    }

    Write-Info "installed uv: $(uv --version)"
}

# ── Install mm from PyPI ────────────────────────────────────────

function Install-Mm {
    $version = $env:MM_VERSION

    if ($version) {
        Write-Info "installing mm-ctx==$version from PyPI..."
        try {
            uv tool install "mm-ctx==$version" --force 2>&1
            Write-Info "mm installed successfully (v$version)"
        } catch {
            Write-Err "failed to install mm-ctx==$version from PyPI"
        }
    } else {
        Write-Info "installing mm-ctx from PyPI (latest)..."
        try {
            uv tool install mm-ctx --force 2>&1
            Write-Info "mm installed successfully"
        } catch {
            Write-Err "failed to install mm-ctx from PyPI"
        }
    }
}

# ── Verify installation ─────────────────────────────────────────

function Test-Installation {
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")

    if (Get-Command mm -ErrorAction SilentlyContinue) {
        $ver = try { mm --version 2>$null } catch { "installed" }
        Write-Info "mm is ready: $ver"
        Write-Info "binary location: $((Get-Command mm).Source)"
    } else {
        Write-Warn "mm was installed but is not in your PATH"
        Write-Warn "you may need to restart your terminal or add the uv tools directory to PATH"
    }
}

# ── Main ─────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  ███╗   ███╗███╗   ███╗" -ForegroundColor Green
Write-Host "  ████╗ ████║████╗ ████║" -ForegroundColor Green
Write-Host "  ██╔████╔██║██╔████╔██║" -ForegroundColor Green
Write-Host "  ██║╚██╔╝██║██║╚██╔╝██║" -ForegroundColor Green
Write-Host "  ██║ ╚═╝ ██║██║ ╚═╝ ██║" -ForegroundColor Green
Write-Host "  ╚═╝     ╚═╝╚═╝     ╚═╝" -ForegroundColor Green
Write-Host ""
Write-Host "  Fast, multimodal file intelligence for agents"
Write-Host ""

Get-Platform
Ensure-Uv
Install-Mm
Test-Installation

Write-Host ""
Write-Info "Get started:"
Write-Info "mm --help"
Write-Info "mm find . --tree"
Write-Host ""
