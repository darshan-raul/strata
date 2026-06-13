"""Strata – TUI laptop intelligence agent."""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual import work
from textual.widgets import Footer, Header, Input, Static
from rich.text import Text

from agent import SystemAnalysis, build_llm, run_analysis
from stats import SystemStats, collect_stats

load_dotenv()

REFRESH_SECS = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    color = "green" if pct < 60 else ("yellow" if pct < 85 else "red")
    bar = f"[{color}]{'█' * filled}[/{color}]{'░' * (width - filled)}"
    return bar


# ── Widgets ───────────────────────────────────────────────────────────────────

class StatsWidget(Static):
    """Left pane: live system stats."""

    stats: reactive[Optional[SystemStats]] = reactive(None, layout=True)

    def render(self) -> Text:
        t = Text()
        t.append("SYSTEM STATS\n\n", style="bold #58a6ff")

        if self.stats is None:
            t.append("Collecting…", style="dim")
            return t

        s = self.stats

        # CPU
        t.append(f"CPU   {_bar(s.cpu_percent)}  {s.cpu_percent:.0f}%\n", style="#e6edf3")
        cores = "  ".join(f"C{i}:{v:.0f}%" for i, v in enumerate(s.cpu_per_core))
        t.append(f"      {cores}\n\n", style="dim #8b949e")

        # RAM
        t.append(
            f"RAM   {_bar(s.ram_percent)}  {s.ram_used_gb:.1f}/{s.ram_total_gb:.1f} GB\n\n",
            style="#e6edf3",
        )

        # Disks
        t.append("DISKS\n", style="bold #8b949e")
        for d in s.disk_usage[:4]:
            mount = d["mount"][:10].ljust(10)
            t.append(
                f"{mount}  {_bar(d['percent'])}  {d['used_gb']:.0f}/{d['total_gb']:.0f} GB\n",
                style="#e6edf3",
            )
        t.append("\n")

        # Battery
        if s.battery_percent is not None:
            icon = "⚡" if s.battery_plugged else "🔋"
            bpct = s.battery_percent
            col = "#3fb950" if bpct > 50 else ("#d29922" if bpct > 20 else "#f85149")
            t.append(f"BATTERY  {icon} {bpct:.0f}%\n\n", style=col)

        # Network
        t.append("NETWORK\n", style="bold #8b949e")
        t.append(f"↑ {s.net_sent_mb:.1f} MB   ↓ {s.net_recv_mb:.1f} MB\n\n", style="#e6edf3")

        # Processes
        t.append("TOP PROCESSES\n", style="bold #8b949e")
        for p in s.top_processes:
            name = (p.get("name") or "?")[:18].ljust(18)
            cpu = p.get("cpu_percent") or 0
            mem = p.get("memory_percent") or 0
            col = "#f85149" if cpu > 50 else "#e6edf3"
            t.append(f"{name}  cpu:{cpu:4.0f}%  mem:{mem:4.1f}%\n", style=col)

        return t


class AnalysisWidget(Static):
    """Right pane: LLM structured analysis."""

    analysis: reactive[Optional[SystemAnalysis]] = reactive(None, layout=True)
    loading: reactive[bool] = reactive(False, layout=True)

    def render(self) -> Text:
        t = Text()
        t.append("AI ANALYSIS\n\n", style="bold #58a6ff")

        if self.loading:
            t.append("⏳  Analyzing…\n", style="dim #8b949e")
            return t

        if self.analysis is None:
            t.append("Waiting for first refresh…\n", style="dim #8b949e")
            return t

        a = self.analysis

        # Severity badge
        sev_style = {"ok": "#3fb950", "warning": "#d29922", "critical": "#f85149"}[a.severity]
        sev_icon  = {"ok": "● OK", "warning": "▲ WARNING", "critical": "✖ CRITICAL"}[a.severity]
        t.append(f"{sev_icon}\n\n", style=f"bold {sev_style}")

        # Summary
        t.append("SUMMARY\n", style="bold #8b949e")
        t.append(f"{a.summary}\n\n", style="#e6edf3")

        # Issues
        if a.issues:
            t.append("ISSUES\n", style="bold #8b949e")
            for issue in a.issues:
                t.append(f"  • {issue}\n", style="#f0883e")
            t.append("\n")

        # Suggestions
        if a.suggestions:
            t.append("SUGGESTIONS\n", style="bold #8b949e")
            for sug in a.suggestions:
                t.append(f"  → {sug}\n", style="#3fb950")

        return t


# ── App ───────────────────────────────────────────────────────────────────────

class StrataApp(App):
    TITLE = "Strata"
    SUB_TITLE = "Laptop Intelligence Agent"
    BINDINGS = [("q", "quit", "Quit"), ("r", "force_refresh", "Refresh")]

    CSS = """
    Screen {
        background: #0d1117;
    }
    Header {
        background: #161b22;
        color: #58a6ff;
    }
    Footer {
        background: #161b22;
        color: #8b949e;
    }
    #main {
        height: 1fr;
    }
    #left-pane {
        width: 48;
        border: solid #30363d;
        margin: 1 0 1 1;
        padding: 1 2;
        background: #0d1117;
    }
    #right-pane {
        width: 1fr;
        border: solid #30363d;
        margin: 1 1 1 1;
        padding: 1 2;
        background: #0d1117;
    }
    #chat {
        dock: bottom;
        margin: 0 1 1 1;
        background: #161b22;
        border: tall #30363d;
        color: #e6edf3;
        padding: 0 2;
    }
    #chat:focus {
        border: tall #58a6ff;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            yield StatsWidget(id="left-pane")
            yield AnalysisWidget(id="right-pane")
        yield Input(placeholder="Ask about your system… (Enter to send, r to refresh, q to quit)", id="chat")
        yield Footer()

    def on_mount(self) -> None:
        self._llm = build_llm()
        self._do_refresh()
        self.set_interval(REFRESH_SECS, self._do_refresh)

    def action_force_refresh(self) -> None:
        self._do_refresh()

    @work(exclusive=True, thread=True)
    def _do_refresh(self) -> None:
        """Collect UI stats; LLM gathers its own via tools (thread worker)."""
        import asyncio

        # UI panel: collect and display stats independently
        stats = collect_stats()
        self.call_from_thread(setattr, self.query_one(StatsWidget), "stats", stats)

        # Agent: calls tools itself to gather what it needs
        analysis_widget = self.query_one(AnalysisWidget)
        self.call_from_thread(setattr, analysis_widget, "loading", True)
        try:
            result = asyncio.run(run_analysis(self._llm))
        except Exception as exc:
            result = SystemAnalysis(
                summary=f"Analysis failed: {exc}",
                issues=[],
                suggestions=["Check your MINIMAX_API_KEY and endpoint env vars."],
                severity="warning",
            )
        finally:
            self.call_from_thread(setattr, analysis_widget, "loading", False)
        self.call_from_thread(setattr, analysis_widget, "analysis", result)

    @work(exclusive=False, thread=True)
    def _ask(self, question: str) -> None:
        """User question → agent calls tools → structured answer."""
        import asyncio

        analysis_widget = self.query_one(AnalysisWidget)
        self.call_from_thread(setattr, analysis_widget, "loading", True)
        try:
            result = asyncio.run(run_analysis(self._llm, question))
        except Exception as exc:
            result = SystemAnalysis(
                summary=f"Error: {exc}",
                issues=[],
                suggestions=["Check your API key / network."],
                severity="warning",
            )
        finally:
            self.call_from_thread(setattr, analysis_widget, "loading", False)
        self.call_from_thread(setattr, analysis_widget, "analysis", result)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if not question:
            return
        event.input.clear()
        self._ask(question)


if __name__ == "__main__":
    StrataApp().run()
