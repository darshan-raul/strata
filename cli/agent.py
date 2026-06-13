"""LangChain agent: bind_tools + manual execution loop + PydanticOutputParser."""
from __future__ import annotations

import os
from typing import Literal

import psutil
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


# ── Output schema ─────────────────────────────────────────────────────────────

class SystemAnalysis(BaseModel):
    summary: str = Field(description="2–3 sentence overall assessment of system health.")
    issues: list[str] = Field(description="Specific problems or concerns found in the stats.")
    suggestions: list[str] = Field(description="Concrete, actionable steps the user can take.")
    severity: Literal["ok", "warning", "critical"] = Field(
        description="ok = healthy, warning = minor concerns, critical = immediate action needed."
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_cpu_stats() -> str:
    """Return current CPU usage — overall percentage and per-core breakdown."""
    overall = psutil.cpu_percent(interval=0.5)
    per_core = psutil.cpu_percent(percpu=True)
    cores = ", ".join(f"C{i}:{v:.0f}%" for i, v in enumerate(per_core))
    return f"CPU overall: {overall:.1f}% | per-core: {cores}"


@tool
def get_memory_stats() -> str:
    """Return current RAM usage in GB and percentage."""
    r = psutil.virtual_memory()
    return (
        f"RAM used: {r.used / 1024**3:.2f} GB / "
        f"{r.total / 1024**3:.2f} GB ({r.percent:.0f}%)"
    )


@tool
def get_disk_stats() -> str:
    """Return disk usage for all mounted partitions."""
    lines: list[str] = []
    for part in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(part.mountpoint)
            lines.append(
                f"{part.mountpoint}: {u.used / 1024**3:.1f} / "
                f"{u.total / 1024**3:.1f} GB ({u.percent:.0f}%)"
            )
        except (PermissionError, OSError):
            pass
    return "\n".join(lines) or "No accessible partitions."


@tool
def get_battery_stats() -> str:
    """Return battery level and whether it is charging."""
    b = psutil.sensors_battery()
    if b is None:
        return "No battery detected (desktop or unsupported)."
    state = "charging" if b.power_plugged else "discharging"
    mins = f", {b.secsleft // 60} min remaining" if not b.power_plugged and b.secsleft > 0 else ""
    return f"Battery: {b.percent:.0f}% ({state}{mins})"


@tool
def get_network_stats() -> str:
    """Return total bytes sent and received since boot."""
    n = psutil.net_io_counters()
    return (
        f"Network (session total): "
        f"↑ {n.bytes_sent / 1024**2:.1f} MB  ↓ {n.bytes_recv / 1024**2:.1f} MB"
    )


@tool
def get_top_processes() -> str:
    """Return the top 6 processes sorted by CPU usage."""
    procs: list[dict] = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    top = sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:6]
    lines = [
        f"{p['name']:20s}  PID:{p['pid']}  "
        f"CPU:{p.get('cpu_percent') or 0:.1f}%  "
        f"MEM:{p.get('memory_percent') or 0:.1f}%"
        for p in top
    ]
    return "\n".join(lines) or "No process data available."


TOOLS = [
    get_cpu_stats,
    get_memory_stats,
    get_disk_stats,
    get_battery_stats,
    get_network_stats,
    get_top_processes,
]
_TOOLS_MAP = {t.name: t for t in TOOLS}

# ── LLM factory ───────────────────────────────────────────────────────────────

def build_llm():
    """Return a ChatOpenAI instance with tools bound."""
    llm = ChatOpenAI(
        api_key=os.environ["MINIMAX_API_KEY"],
        base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.chat/v1"),
        model=os.environ.get("MINIMAX_MODEL", "MiniMax-M3"),
        temperature=0.3,
        max_tokens=1024,
    )
    return llm.bind_tools(TOOLS)


# ── Agent loop ────────────────────────────────────────────────────────────────

_parser = PydanticOutputParser(pydantic_object=SystemAnalysis)

_SYSTEM = SystemMessage(content=(
    "You are a concise laptop performance analyst. "
    "Call the available tools to gather the system metrics relevant to the user's question, "
    "then output ONLY a JSON object — no prose, no markdown fences — matching this schema:\n\n"
    + _parser.get_format_instructions()
))


async def run_analysis(llm_with_tools, question: str = "General health check.") -> SystemAnalysis:
    """Manual tool-call loop → PydanticOutputParser. No AgentExecutor."""
    messages = [_SYSTEM, HumanMessage(content=question)]

    while True:
        response: AIMessage = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # Final text response — parse into SystemAnalysis
            break

        # Execute every tool the LLM requested
        for tc in response.tool_calls:
            tool_fn = _TOOLS_MAP[tc["name"]]
            result = tool_fn.invoke(tc["args"])
            messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

    return _parser.parse(response.content)
