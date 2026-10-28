"""Environment doctor — safe inspection only (no installs, no large downloads)."""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def _mem_info() -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith(("MemTotal:", "MemAvailable:")):
                    key, val, *_ = line.split()
                    info[key.rstrip(":")] = f"{int(val) // 1024} MiB"
    except OSError:
        info["error"] = "meminfo unavailable"
    return info


def run_doctor() -> dict[str, Any]:
    system = platform.system()
    report: dict[str, Any] = {
        "os": {
            "system": system,
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "preferred": "3.11 or 3.12",
            "ok": sys.version_info[:2] >= (3, 11),
        },
        "memory": _mem_info(),
        "cwd": str(Path.cwd()),
        "workspace_exists": Path("workspace").exists(),
        "daw": {
            "fl_studio": "N/A — not macOS" if system != "Darwin" else "probe required",
            "postfader": "N/A — not installed in this environment",
            "iac_midi": "N/A — macOS IAC Driver only",
            "simulation_mode": True,
            "manual_import_mode": True,
        },
        "tools": {
            "git": bool(shutil.which("git")),
            "ffmpeg": bool(shutil.which("ffmpeg")),
        },
        "env_flags": {
            "ALLOW_CLOUD_AUDIO": os.getenv("ALLOW_CLOUD_AUDIO", "false"),
            "ALLOW_CLOUD_LLM": os.getenv("ALLOW_CLOUD_LLM", "false"),
            "DAW_MODE": os.getenv("DAW_MODE", "simulation"),
        },
        "recommendations": [
            "Phase 0 runs fully in simulation / MIDI-export mode on this Linux cloud VM.",
            "FL Studio + PostFader + IAC must be configured on the user's Apple Silicon Mac mini.",
            "Do not install large audio models or download datasets until user approval (Phase 2+).",
        ],
    }
    return report
