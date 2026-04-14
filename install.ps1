# Install mm — high-performance multimodal context management CLI
#
# Usage:
#   irm https://vlm-run.github.io/mm/install/install.ps1 | iex
#
# Options (via env vars):
#   $env:MM_VERSION = "0.4.0"    Install a specific version (default: latest published)
#   $env:MM_FROM_GIT = "1"       Build from source (requires SSH + Rust toolchain)
#   $env:MM_GIT_REF = "v0.4.0"  Git ref to build from (default: latest, requires MM_FROM_GIT=1)
#   $env:MM_SKIP_VERIFY = "1"    Skip checksum verification (not recommended)

$ErrorActionPreference = "Stop"

$BaseUrl = "https://vlm-run.github.io/mm/install"

function Write-Info  { param($Msg) Write-Host "info: $Msg" -ForegroundColor Green }
function Write-Warn  { param($Msg) Write-Host "warn: $Msg" -ForegroundColor Yellow }
function Write-Err   { param($Msg) Write-Host "error: $Msg" -ForegroundColor Red; exit 1 }

# ── Platform detection ───────────────────────────────────────────

function Get-Platform {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    switch ($arch) {
        "X64"   { $script:PlatformArch = "x86_64"; $script:WheelPattern = "win_amd64" }
        "Arm64" { $script:PlatformArch = "aarch64"; $script:WheelPattern = "win_arm64" }
        default { Write-Err "unsupported architecture: $arch. mm supports x86_64 and aarch64." }
    }
    $script:Platform = "windows-$script:PlatformArch"
    Write-Info "detected platform: $script:Platform"
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

# ── Ensure Rust (source builds only) ────────────────────────────

function Ensure-Rust {
    if (Get-Command rustc -ErrorAction SilentlyContinue) {
        Write-Info "found rust: $(rustc --version)"
        return
    }

    Write-Info "rust not found — installing via rustup..."
    $rustupInit = "$env:TEMP\rustup-init.exe"
    Invoke-WebRequest -Uri "https://win.rustup.rs/$script:PlatformArch" -OutFile $rustupInit
    & $rustupInit -y
    Remove-Item $rustupInit -ErrorAction SilentlyContinue

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")

    if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
        Write-Err "rust installation succeeded but 'rustc' not found in PATH"
    }

    Write-Info "installed rust: $(rustc --version)"
}

# ── Checksum verification ────────────────────────────────────────

function Test-Checksum {
    param($File, $Expected)

    $actual = (Get-FileHash -Path $File -Algorithm SHA256).Hash.ToLower()

    if ($actual -eq $Expected) {
        Write-Info "checksum verified: $actual"
        return $true
    } else {
        Write-Host ""
        Write-Host "  CHECKSUM MISMATCH" -ForegroundColor Red
        Write-Host "  expected: $Expected" -ForegroundColor Cyan
        Write-Host "  actual:   $actual" -ForegroundColor Cyan
        Write-Host ""
        Write-Err "checksum verification failed — the download may be corrupted or tampered with"
    }
}

# ── Download & verify wheel ──────────────────────────────────────

function Get-Wheel {
    $version = if ($env:MM_VERSION) { $env:MM_VERSION } else { "latest" }
    $manifestUrl = "$BaseUrl/$version/SHA256SUMS"
    $tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) "mm-install-$(Get-Random)"
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

    Write-Info "fetching manifest for version: $version..."
    try {
        Invoke-WebRequest -Uri $manifestUrl -OutFile "$tmpDir\SHA256SUMS" -ErrorAction Stop
    } catch {
        if ($version -eq "latest") {
            Write-Err "could not fetch manifest from $manifestUrl`nNo pre-built wheels found. Install from source with:`n  `$env:MM_FROM_GIT = '1'; irm $BaseUrl/install.ps1 | iex"
        } else {
            Write-Err "version $version not found at $manifestUrl"
        }
    }

    # Find the wheel for this platform
    $manifest = Get-Content "$tmpDir\SHA256SUMS"
    $match = $manifest | Where-Object { $_ -match $script:WheelPattern } | Select-Object -First 1

    if (-not $match) {
        Write-Err "no pre-built wheel for $script:Platform in version $version`nInstall from source with:`n  `$env:MM_FROM_GIT = '1'; irm $BaseUrl/install.ps1 | iex"
    }

    $parts = $match -split '\s+', 2
    $expectedHash = $parts[0]
    $wheelName = $parts[1].TrimStart("*")
    $wheelUrl = "$BaseUrl/$version/$wheelName"

    Write-Info "downloading $wheelName..."
    Invoke-WebRequest -Uri $wheelUrl -OutFile "$tmpDir\$wheelName"

    # Verify checksum
    if ($env:MM_SKIP_VERIFY -ne "1") {
        Test-Checksum -File "$tmpDir\$wheelName" -Expected $expectedHash
    } else {
        Write-Warn "checksum verification skipped (MM_SKIP_VERIFY=1)"
    }

    $script:WheelPath = "$tmpDir\$wheelName"
    Write-Info "wheel ready: $wheelName"
}

# ── Install mm ───────────────────────────────────────────────────

function Install-Mm {
    $fromGit = $env:MM_FROM_GIT -eq "1"

    if ($fromGit) {
        Ensure-Rust

        $repo = "git+ssh://git@github.com/vlm-run/mm.git"
        $gitRef = $env:MM_GIT_REF

        if ($gitRef) {
            $source = "$repo@$gitRef"
            Write-Info "installing mm from source ($gitRef)..."
        } else {
            $source = $repo
            Write-Info "installing mm from source (latest)..."
        }

        try {
            uv tool install mm --from $source --force 2>&1
            Write-Info "mm installed successfully (from source)"
        } catch {
            Write-Err "failed to install mm — do you have SSH access to github.com/vlm-run/mm?"
        }
    } else {
        Get-Wheel

        try {
            uv tool install mm --from $script:WheelPath --force 2>&1
            Write-Info "mm installed successfully"
        } catch {
            Write-Err "failed to install mm from wheel"
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
Write-Host "  mm installer" -NoNewline
Write-Host ""
Write-Host "  high-performance multimodal context management"
Write-Host ""

Get-Platform
Ensure-Uv
Install-Mm
Test-Installation

Write-Host ""
Write-Info "Get started:"
Write-Info "  mm --help"
Write-Info "  mm find . --tree"
Write-Host ""
