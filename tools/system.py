"""ODIN Agent - System Tool.

Liefert grundlegende Informationen ueber den Odin-Server:
Hostname, OS, CPU, RAM, Disk, GPU (via nvidia-smi), Uptime, Prozesse.
Alle Informationen werden als strukturierte Daten zurueckgegeben.
"""
from __future__ import annotations

import platform
import subprocess
import time
from pathlib import Path

from tools.base import BaseTool, ToolResult


def _run(cmd: list[str], timeout: int = 3):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        ).stdout.strip()
    except Exception:
        return None




class SystemTool(BaseTool):
    name = "system"
    description = (
        "Liefert Informationen ueber den Odin-Server: Hostname, OS, CPU, "
        "RAM, Disk, GPU-Temperatur, GPU-Auslastung, Uptime, Top-Prozesse."
    )
    parameters = {
        "type": "object",
        "properties": {
            "info": {
                "type": "string",
                "enum": ["all", "gpu", "cpu", "mem", "disk", "uptime", "processes"],
                "description": "Welche Information abgefragt werden soll (default: all).",
            }
        },
        "required": ["info"],
    }

    def _gpu(self) -> list[dict]:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode != 0:
            return []
        gpus = []
        for line in out.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 6:
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "temperature_c": int(parts[2]),
                        "utilization_pct": int(parts[3]),
                        "memory_used_mb": int(parts[4]),
                        "memory_total_mb": int(parts[5]),
                    }
                )
        return gpus

    def _mem(self) -> dict:
        try:
            raw = _read("/proc/meminfo")
            if not raw:
                return {}
            lines = raw.splitlines()
            total_kb = int(lines[0].split()[1])
            avail_kb = int([l for l in lines if l.startswith("MemAvailable")][0].split()[1])
            return {
                "total_gb": round(total_kb / 1024 / 1024, 1),
                "available_gb": round(avail_kb / 1024 / 1024, 1),
            }
        except (IndexError, ValueError):
            return {}

    def _disk(self) -> list[dict]:
        out = subprocess.run(
            ["df", "-h", "--output=source,filesystem,size,used,avail,use%,target"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode != 0:
            return []
        lines = [l.strip() for l in out.stdout.strip().splitlines() if l.strip()]
        headers = [h.strip() for h in lines[0].split()]
        disks = []
        for raw in lines[1:]:
            # 'target' kann Leerzeichen enthalten -> Muster: ...  <use%> <target>
            parts = raw.split()
            if len(parts) < 6:
                continue
            target = " ".join(parts[5:])
            try:
                disks.append(
                    {
                        "source": parts[0],
                        "size": parts[1],
                        "used": parts[2],
                        "avail": parts[3],
                        "use_pct": parts[4],
                        "mount": target,
                    }
                )
            except Exception:
                continue
        return disks

    def _uptime(self) -> dict:
        try:
            raw = float(_read("/proc/uptime").split()[0])
            return {"uptime_s": int(raw), "uptime_human": self._human(int(raw))}
        except (ValueError, IndexError):
            return {}

    @staticmethod
    def _human(seconds: int) -> str:
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        return f"{days}d {hours}h {mins}m {secs}s"

    def _processes(self, top: int = 15) -> list[dict]:
        out = subprocess.run(
            ["ps", "-eo", "pcpu,pmem,pid,comm", "--sort=-pcpu"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if out.returncode != 0:
            return []
        procs = []
        for i, raw in enumerate(out.stdout.strip().splitlines()):
            if i == 0:
                continue
            parts = raw.split(None, 3)
            if len(parts) < 4:
                continue
            try:
                procs.append(
                    {
                        "cpu_pct": float(parts[0]),
                        "mem_pct": float(parts[1]),
                        "pid": int(parts[2]),
                        "name": parts[3],
                    }
                )
            except ValueError:
                continue
            if len(procs) >= top:
                break
        return procs

    def _cpu(self) -> dict:
        model = _read("/proc/cpuinfo")
        model_name = None
        for line in (model or "").splitlines():
            if line.startswith("model name"):
                model_name = line.split(":", 1)[1].strip()
                break
        return {"model": model_name or platform.processor() or None}

    def run(self, info: str = "all") -> ToolResult:
        data = {}
        if info in ("all", "gpu"):
            data["gpu"] = self._gpu()
        if info in ("all", "cpu"):
            data["cpu"] = self._cpu()
        if info in ("all", "mem"):
            data["memory"] = self._mem()
        if info in ("all", "disk"):
            data["disk"] = self._disk()
        if info in ("all", "uptime"):
            data["uptime"] = self._uptime()
        if info in ("all", "processes"):
            data["processes"] = self._processes()

        data["hostname"] = platform.node()
        data["os"] = f"{platform.system()} {platform.release()}"
        return ToolResult.ok(data=data)


def os_cpu_count() -> int | None:
    try:
        return int(_read("/proc/cpuinfo").split("processor").__len__() )
    except (AttributeError, ValueError):
        return None