"""System statistics collection using psutil."""
from __future__ import annotations

import psutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class SystemStats:
    cpu_percent: float
    cpu_per_core: list[float]
    ram_used_gb: float
    ram_total_gb: float
    ram_percent: float
    disk_usage: list[dict]          # {mount, used_gb, total_gb, percent}
    battery_percent: Optional[float]
    battery_plugged: Optional[bool]
    net_sent_mb: float
    net_recv_mb: float
    top_processes: list[dict]       # {pid, name, cpu_percent, memory_percent}


def collect_stats() -> SystemStats:
    cpu_overall = psutil.cpu_percent(interval=0.5)
    cpu_cores = psutil.cpu_percent(percpu=True)

    ram = psutil.virtual_memory()

    disks: list[dict] = []
    for part in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "used_gb": u.used / 1024 ** 3,
                "total_gb": u.total / 1024 ** 3,
                "percent": u.percent,
            })
        except (PermissionError, OSError):
            pass

    batt = psutil.sensors_battery()
    net = psutil.net_io_counters()

    procs: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    top = sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:6]

    return SystemStats(
        cpu_percent=cpu_overall,
        cpu_per_core=cpu_cores,
        ram_used_gb=ram.used / 1024 ** 3,
        ram_total_gb=ram.total / 1024 ** 3,
        ram_percent=ram.percent,
        disk_usage=disks,
        battery_percent=batt.percent if batt else None,
        battery_plugged=batt.power_plugged if batt else None,
        net_sent_mb=net.bytes_sent / 1024 ** 2,
        net_recv_mb=net.bytes_recv / 1024 ** 2,
        top_processes=top,
    )


def stats_to_text(s: SystemStats) -> str:
    """Serialize stats to plain text for the LLM prompt."""
    lines = [
        f"CPU: {s.cpu_percent:.1f}% overall | per-core: {', '.join(f'{c:.0f}%' for c in s.cpu_per_core)}",
        f"RAM: {s.ram_used_gb:.2f} / {s.ram_total_gb:.2f} GB ({s.ram_percent:.0f}%)",
    ]
    for d in s.disk_usage:
        lines.append(
            f"Disk [{d['mount']}]: {d['used_gb']:.1f} / {d['total_gb']:.1f} GB ({d['percent']:.0f}%)"
        )
    if s.battery_percent is not None:
        state = "charging" if s.battery_plugged else "discharging"
        lines.append(f"Battery: {s.battery_percent:.0f}% ({state})")
    lines.append(f"Network (session): ↑{s.net_sent_mb:.1f} MB  ↓{s.net_recv_mb:.1f} MB")
    lines.append("Top Processes by CPU:")
    for p in s.top_processes:
        lines.append(
            f"  {p['name']:20s}  PID:{p['pid']}  "
            f"CPU:{p.get('cpu_percent') or 0:.1f}%  "
            f"MEM:{p.get('memory_percent') or 0:.1f}%"
        )
    return "\n".join(lines)
