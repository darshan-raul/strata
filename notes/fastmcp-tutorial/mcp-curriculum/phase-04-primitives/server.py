# phase-04-primitives/server.py
#
# PURPOSE: One server demonstrating all four MCP primitives:
#   Tools     — actions the LLM can invoke
#   Resources — data the app/user can read (addressed by URI)
#   Prompts   — reusable message templates
#   Context   — logging, progress, reading resources from within tools
#
# Run standalone:    uv run python phase-04-primitives/server.py
# Test via client:   uv run python phase-04-primitives/client.py

import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from fastmcp import FastMCP, Context

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP("primitives-demo")

# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — TOOLS
#
# Tools are functions the LLM calls to DO things.
# Key advanced patterns shown here:
#   A. Async tools (required when you do I/O like boto3, httpx, etc.)
#   B. Context injection for logging + progress
#   C. Returning structured data (dict/list) not just strings
#   D. Tool that reads a Resource (cross-primitive usage)
# ═════════════════════════════════════════════════════════════════════════════

# ── A. Sync tool (simple, no I/O) ────────────────────────────────────────────
@mcp.tool()
def calculate_bmi(weight_kg: float, height_m: float) -> dict:
    """
    Calculate Body Mass Index (BMI) from weight and height.
    Returns BMI value and category.
    """
    if height_m <= 0 or weight_kg <= 0:
        raise ValueError("Weight and height must be positive numbers.")

    bmi = weight_kg / (height_m ** 2)

    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25.0:
        category = "Normal weight"
    elif bmi < 30.0:
        category = "Overweight"
    else:
        category = "Obese"

    # Returning a dict → FastMCP serializes it to JSON text on the wire
    # The LLM receives: {"bmi": 22.86, "category": "Normal weight"}
    return {"bmi": round(bmi, 2), "category": category}


# ── B. Async tool with Context (logging + progress) ──────────────────────────
@mcp.tool()
async def process_report(report_name: str, ctx: Context) -> str:
    """
    Simulate processing a long-running report.
    Demonstrates async tools, ctx.info() logging, and ctx.report_progress().
    """
    # ctx.info() sends a JSON-RPC notification to the client:
    # {"method": "notifications/message", "params": {"level": "info", ...}}
    # The host (e.g. Claude Desktop) shows this as a log in its UI.
    await ctx.info(f"Starting report: {report_name}")

    total_steps = 5
    for step in range(1, total_steps + 1):
        await asyncio.sleep(0.1)  # simulate work

        # ctx.report_progress() sends a progress notification:
        # {"method": "notifications/progress", "params": {"progress": 2, "total": 5}}
        await ctx.report_progress(step, total_steps)
        await ctx.debug(f"Completed step {step}/{total_steps}")

    await ctx.info(f"Report '{report_name}' complete.")
    return f"Report '{report_name}' processed at {datetime.now().isoformat()}"


# ── C. Tool with Pydantic model + complex return type ────────────────────────
class ServerSpec(BaseModel):
    name: str = Field(description="Server instance name")
    cpu_cores: int = Field(description="Number of CPU cores", ge=1, le=128)
    ram_gb: int = Field(description="RAM in GB", ge=1, le=1024)
    region: str = Field(default="us-east-1", description="AWS region")

@mcp.tool()
def estimate_cost(spec: ServerSpec) -> dict:
    """
    Estimate monthly cloud cost for a server specification.
    Prices are illustrative, not real AWS pricing.
    """
    # Simplified cost formula
    cpu_cost  = spec.cpu_cores * 15.0   # $15/core/month
    ram_cost  = spec.ram_gb * 2.5       # $2.5/GB/month
    total     = cpu_cost + ram_cost

    return {
        "spec": spec.model_dump(),
        "monthly_cost_usd": round(total, 2),
        "breakdown": {
            "cpu": round(cpu_cost, 2),
            "ram": round(ram_cost, 2),
        }
    }


# ── D. Tool that reads a Resource internally ─────────────────────────────────
@mcp.tool()
async def summarize_config(ctx: Context) -> str:
    """
    Read the app config resource and summarize its contents.
    Demonstrates cross-primitive usage: a Tool reading a Resource.
    """
    await ctx.info("Reading app config resource...")

    # ctx.read_resource() makes a resources/read call internally
    # FastMCP 3.x returns a ResourceResult object:
    #   result.contents        → list of ResourceContent items
    #   result.contents[0].content → the raw text/bytes
    resource_result = await ctx.read_resource("config://app/settings")
    config_text = resource_result.contents[0].content
    config = json.loads(config_text)

    lines = [f"App Configuration Summary:"]
    for key, value in config.items():
        lines.append(f"  • {key}: {value}")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RESOURCES
#
# Resources are read-only data sources addressed by URI.
# URI scheme is up to you — common patterns:
#   config://...    → configuration data
#   db://...        → database records
#   file://...      → file contents
#   {service}://... → any namespace you define
#
# Two types:
#   Static URI:   @mcp.resource("config://app/settings")
#   Template URI: @mcp.resource("users://{user_id}/profile")
#                 → URI parameter becomes a function argument
# ═════════════════════════════════════════════════════════════════════════════

# ── Static Resource ───────────────────────────────────────────────────────────
@mcp.resource("config://app/settings")
def get_app_settings() -> str:
    """
    Returns the application's current configuration as JSON.
    Static URI — always the same data (or regenerated each call).
    """
    settings = {
        "app_name": "primitives-demo",
        "version": "1.0.0",
        "environment": "development",
        "max_connections": 100,
        "log_level": "INFO",
        "generated_at": datetime.now().isoformat(),
    }
    # Resources return strings (text) or bytes (blob).
    # FastMCP infers the MIME type from what you return.
    return json.dumps(settings, indent=2)


# ── Dynamic Resource (URI Template) ──────────────────────────────────────────
@mcp.resource("users://{user_id}/profile")
def get_user_profile(user_id: str) -> str:
    """
    Returns a user's profile by ID.
    URI template — {user_id} becomes a function parameter.
    Client calls: resources/read with URI = "users://42/profile"
    """
    # In a real server this would query a DB.
    # We simulate a small in-memory dataset.
    users = {
        "1": {"name": "Darshan",  "role": "engineer",  "team": "platform"},
        "2": {"name": "Priya",    "role": "designer",  "team": "product"},
        "3": {"name": "Arjun",    "role": "manager",   "team": "engineering"},
    }

    user = users.get(user_id)
    if not user:
        raise ValueError(f"User '{user_id}' not found.")

    return json.dumps({"user_id": user_id, **user}, indent=2)


# ── Resource that returns structured logs ────────────────────────────────────
@mcp.resource("logs://app/recent")
def get_recent_logs() -> str:
    """
    Returns the last N application log entries.
    Demonstrates that resources can return any text-based format.
    """
    logs = [
        {"ts": "2026-06-19T10:00:01Z", "level": "INFO",  "msg": "Server started"},
        {"ts": "2026-06-19T10:00:05Z", "level": "DEBUG", "msg": "First connection established"},
        {"ts": "2026-06-19T10:01:22Z", "level": "INFO",  "msg": "Tool 'greet' called"},
        {"ts": "2026-06-19T10:05:44Z", "level": "WARN",  "msg": "High memory usage detected"},
        {"ts": "2026-06-19T10:06:00Z", "level": "INFO",  "msg": "GC cycle completed"},
    ]
    return json.dumps(logs, indent=2)


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PROMPTS
#
# Prompts are reusable message templates.
# The server exposes them; the user/host chooses when to use one.
# They return: str | list[Message]
#
#   str           → becomes a single user message
#   list[Message] → full conversation (system + user + assistant turns)
#
# The client calls: prompts/get with the prompt name + arguments.
# FastMCP returns a GetPromptResult with messages ready for an LLM.
# ═════════════════════════════════════════════════════════════════════════════

from fastmcp.prompts import Message

# ── Simple prompt (returns a string → single user message) ───────────────────
@mcp.prompt()
def analyze_cost(service_name: str, budget_usd: float) -> str:
    """
    Generate a prompt asking the LLM to analyze cloud costs for a service.
    """
    return (
        f"Analyze the cloud infrastructure costs for the '{service_name}' service. "
        f"Our monthly budget is ${budget_usd:.2f}. "
        f"Identify cost optimization opportunities and suggest at least 3 specific "
        f"actions we can take to reduce spending without impacting reliability."
    )


# ── Multi-turn prompt (returns list of Messages) ──────────────────────────────
@mcp.prompt()
def debug_session(error_message: str, language: str = "Python") -> list[Message]:
    """
    Set up a debugging conversation with a system context + initial user message.
    Returns a full message list — system + user — ready to send to an LLM.
    """
    return [
        Message(
            role="user",
            content=(
                f"I'm debugging a {language} application and encountered this error:\n\n"
                f"```\n{error_message}\n```\n\n"
                f"Please help me understand what caused this error and how to fix it. "
                f"Walk me through step by step."
            )
        )
    ]


# ── Prompt with dynamic content from context ─────────────────────────────────
@mcp.prompt()
def aws_incident_response(service: str, severity: str = "medium") -> list[Message]:
    """
    Generate an incident response prompt for an AWS service issue.
    severity can be: low, medium, high, critical
    """
    severity_emoji = {"low": "🟡", "medium": "🟠", "high": "🔴", "critical": "🚨"}
    emoji = severity_emoji.get(severity, "🟠")

    system_content = (
        "You are an AWS Site Reliability Engineer with deep expertise in "
        "incident response, AWS services, and production systems. "
        "Provide clear, actionable guidance under pressure."
    )

    user_content = (
        f"{emoji} INCIDENT ALERT — Severity: {severity.upper()}\n"
        f"Affected service: AWS {service}\n\n"
        f"Please provide:\n"
        f"1. Immediate triage steps (first 5 minutes)\n"
        f"2. Likely root causes to investigate\n"
        f"3. Mitigation strategies\n"
        f"4. Escalation criteria\n"
        f"5. Post-incident review checklist"
    )

    return [
        Message(role="user", content=system_content + "\n\n" + user_content)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    mcp.run(transport="stdio")
