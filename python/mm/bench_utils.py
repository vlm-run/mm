"""Host system introspection for benchmark provenance.

Captures hardware and software details relevant to benchmark reproducibility:
OS, architecture, CPU, RAM, GPUs (multi-GPU enumeration with compute
capability), CUDA, container runtime, Python, mm version, and the active
LLM profile.

Used by ``mm bench --host-info``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Optional


def _run(cmd: list[str], timeout: float = 3.0) -> Optional[str]:
    """Run a command and return stripped stdout, or None on failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _parse_int_or_zero(s: str) -> int:
    """Parse an int, returning 0 if the value is non-numeric (e.g. '[N/A]')."""
    s = s.strip()
    return int(s) if s.isdigit() else 0


def _detect_os() -> str:
    """Return a human-readable OS name (e.g. 'Ubuntu 24.04.4 LTS', 'macOS 14.5')."""
    import platform

    system = platform.system().lower()
    if system == "linux":
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
        except Exception:
            pass
        return f"Linux {platform.release()}"
    if system == "darwin":
        return f"macOS {platform.mac_ver()[0]}".strip()
    return platform.platform()


def _detect_cpu() -> str:
    """Return the CPU model string.

    Handles x86 Linux (``model name`` in ``/proc/cpuinfo``), ARM Linux
    (no ``model name`` — falls back to ``lscpu``), and macOS.
    """
    import platform

    system = platform.system().lower()
    if system == "darwin":
        out = _run(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=2)
        if out:
            return out
    elif system == "linux":
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            pass
        out = _run(["lscpu"], timeout=2)
        if out:
            for line in out.splitlines():
                if line.startswith("Model name:"):
                    return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def _detect_ram_bytes() -> int:
    """Return total RAM in bytes, or 0 if undetectable."""
    import platform

    system = platform.system().lower()
    if system == "darwin":
        out = _run(["sysctl", "-n", "hw.memsize"], timeout=2)
        if out and out.isdigit():
            return int(out)
    elif system == "linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024  # kiB → bytes
        except Exception:
            pass
    return 0


def _detect_gpus() -> list[dict[str, Any]]:
    """Detect attached GPUs via ``nvidia-smi``, plus Apple Silicon fallback.

    Returns a list of dicts with keys ``vendor``, ``index``, ``name``,
    ``memory_mib``, ``driver``, ``compute_cap``. ``memory_mib`` is 0 when
    the device reports ``[N/A]`` (e.g. unified-memory devices like GB10).
    On Apple Silicon, returns a single ``apple`` entry naming the chip.
    """
    import platform

    gpus: list[dict[str, Any]] = []

    out = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,driver_version,compute_cap",
            "--format=csv,noheader,nounits",
        ]
    )
    if out:
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpus.append(
                    {
                        "vendor": "nvidia",
                        "index": _parse_int_or_zero(parts[0]),
                        "name": parts[1],
                        "memory_mib": _parse_int_or_zero(parts[2]),
                        "driver": parts[3],
                        "compute_cap": parts[4] if len(parts) >= 5 else "",
                    }
                )

    if not gpus and platform.system().lower() == "darwin" and platform.machine() == "arm64":
        chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"], timeout=2) or "Apple Silicon"
        gpus.append({"vendor": "apple", "name": chip})

    return gpus


def _detect_cuda() -> Optional[str]:
    """Return the CUDA version.

    Prefers ``nvcc --version`` (toolkit, e.g. ``13.0.88``), falls back to
    ``nvidia-smi`` (driver-supported version, e.g. ``13.0``).
    """
    out = _run(["nvcc", "--version"], timeout=2)
    if out:
        m = re.search(r"release\s+([\d.]+)", out)
        if m:
            return m.group(1)
    out = _run(["nvidia-smi"], timeout=3)
    if out:
        m = re.search(r"CUDA Version:\s*([\d.]+)", out)
        if m:
            return m.group(1)
    return None


def _detect_container() -> Optional[str]:
    """Detect the container runtime (docker, kubernetes, lxc), or None on bare metal."""
    if Path("/.dockerenv").exists():
        return "docker"
    try:
        cgroup = Path("/proc/1/cgroup").read_text()
    except Exception:
        return None
    if "docker" in cgroup:
        return "docker"
    if "kubepods" in cgroup:
        return "kubernetes"
    if "lxc" in cgroup:
        return "lxc"
    return None


def collect_host_info() -> dict[str, Any]:
    """Collect host system information for benchmark provenance.

    Returns:
        Dict with platform/arch/hostname/os/kernel, cpu/cpu_threads/ram_bytes,
        gpus (list)/cuda, container, python, mm_version, and profile (or None).
    """
    import os as _os
    import platform

    info: dict[str, Any] = {
        "platform": platform.system().lower(),
        "arch": platform.machine(),
        "hostname": platform.node(),
        "kernel": platform.release(),
        "os": _detect_os(),
        "cpu": _detect_cpu(),
        "cpu_threads": _os.cpu_count() or 0,
        "ram_bytes": _detect_ram_bytes(),
        "gpus": _detect_gpus(),
        "cuda": _detect_cuda(),
        "python": platform.python_version(),
    }

    if container := _detect_container():
        info["container"] = container

    try:
        from mm import __version__

        info["mm_version"] = __version__
    except Exception:
        info["mm_version"] = "unknown"

    try:
        from mm.profile import get_profile

        p = get_profile()
        info["profile"] = {
            "name": p.name,
            "base_url": p.base_url,
            "model": p.model,
        }
    except Exception:
        info["profile"] = None

    return info


def render_host_info_rich(info: dict[str, Any], *, to_stderr: bool = False) -> None:
    """Render host info as a Rich panel."""
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    from mm.display import console, format_size, output_console

    target = console if to_stderr else output_console

    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column(justify="right", no_wrap=True)
    table.add_column()

    table.add_row("Platform", f"{info['platform']}/{info['arch']} ({info['kernel']})")
    table.add_row("OS", info["os"])
    table.add_row("Hostname", info["hostname"] or "—")
    table.add_row("CPU", f"{info['cpu']} ({info['cpu_threads']} threads)")
    if info["ram_bytes"]:
        table.add_row("RAM", format_size(info["ram_bytes"]))

    gpus = info.get("gpus") or []
    if gpus:
        for i, g in enumerate(gpus):
            label = "GPU" if i == 0 else ""
            if g.get("vendor") == "nvidia":
                mem = format_size(g["memory_mib"] * 1024 * 1024) if g["memory_mib"] else "N/A"
                line = f"[{g['index']}] {g['name']} ({mem})  driver={g['driver']}"
                if g.get("compute_cap"):
                    line += f"  sm_{g['compute_cap'].replace('.', '')}"
                table.add_row(label, line)
            else:
                table.add_row(label, g.get("name", "unknown"))
    else:
        table.add_row("GPU", "—")

    table.add_row("CUDA", info.get("cuda") or "—")

    if info.get("container"):
        table.add_row("Container", info["container"])

    table.add_row("Python", info["python"])
    table.add_row("mm", f"v{info['mm_version']}")

    p = info.get("profile")
    if p:
        table.add_row("Profile", p["name"])
        table.add_row("base_url", p["base_url"])
        table.add_row("model", p["model"])

    target.print(Panel(table, title="[bold]mm host info[/bold]", box=box.ROUNDED))


def render_host_info(info: dict[str, Any], *, fmt: str, to_stderr: bool = False) -> None:
    """Print host info and exit. Supports ``rich`` (default) and ``json`` formats."""
    if fmt != "rich":
        from mm.display import emit_csv, emit_tsv, json_dumps, resolve_stderr

        if fmt == "json":
            print(json_dumps(info), file=resolve_stderr(to_stderr))
            return
        elif fmt == "tsv":
            emit_tsv([info], stderr=to_stderr)
            return
        elif fmt == "csv":
            emit_csv([info], stderr=to_stderr)
            return

    render_host_info_rich(info, to_stderr=to_stderr)
