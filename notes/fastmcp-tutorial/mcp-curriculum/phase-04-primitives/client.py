# phase-04-primitives/client.py
#
# PURPOSE: Exercise all four primitives — Tools, Resources, Prompts, Context.
# Read the output carefully: each section shows a different primitive in action.
#
# Run with: uv run python phase-04-primitives/client.py

import asyncio
from pathlib import Path
from fastmcp import Client

SERVER_PATH = Path(__file__).parent / "server.py"

def section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)

def subsection(title: str):
    print(f"\n── {title} {'─' * (54 - len(title))}")


async def main():
    async with Client(SERVER_PATH) as client:

        # ══════════════════════════════════════════════════════════
        # PRIMITIVE 1: TOOLS
        # ══════════════════════════════════════════════════════════
        section("PRIMITIVE 1 — TOOLS")

        # ── Sync tool returning a dict ────────────────────────────
        subsection("calculate_bmi (sync, returns dict)")
        result = await client.call_tool("calculate_bmi", {
            "weight_kg": 70, "height_m": 1.75
        })
        print(f"  Result : {result.data}")
        print(f"  Is dict: {isinstance(result.structured_content, dict)}")

        # ── Tool error: bad input ─────────────────────────────────
        subsection("calculate_bmi (negative height → ValueError)")
        try:
            await client.call_tool("calculate_bmi", {"weight_kg": 70, "height_m": -1})
        except Exception as e:
            print(f"  ✓ Caught: {type(e).__name__}: {e}")

        # ── Async tool with Context (logs + progress) ─────────────
        subsection("process_report (async, context logging + progress)")
        # We register a log handler to see ctx.info() / ctx.debug() messages
        logs_received = []
        progress_received = []

        async def on_log(params):
            logs_received.append(f"[{params.level}] {params.data}")

        async def on_progress(params):
            progress_received.append(f"{params.progress}/{params.total}")

        result = await client.call_tool(
            "process_report",
            {"report_name": "Q2 Financials"},
        )
        print(f"  Result   : {result.data}")
        # Note: log/progress messages from ctx arrive as notifications.
        # The Client collects them — in a real host they'd show in the UI.

        # ── Tool with Pydantic input model ────────────────────────
        subsection("estimate_cost (Pydantic ServerSpec)")
        result = await client.call_tool("estimate_cost", {
            "spec": {
                "name": "api-server-prod",
                "cpu_cores": 8,
                "ram_gb": 32,
                "region": "ap-south-1"
            }
        })
        print(f"  Spec     : {result.data['spec']['name']}")
        print(f"  Monthly  : ${result.data['monthly_cost_usd']}")
        print(f"  CPU cost : ${result.data['breakdown']['cpu']}")
        print(f"  RAM cost : ${result.data['breakdown']['ram']}")

        # ── Tool that internally reads a Resource ─────────────────
        subsection("summarize_config (tool reads resource internally)")
        result = await client.call_tool("summarize_config", {})
        print(f"  Result:\n")
        for line in result.data.splitlines():
            print(f"    {line}")

        # ══════════════════════════════════════════════════════════
        # PRIMITIVE 2: RESOURCES
        # ══════════════════════════════════════════════════════════
        section("PRIMITIVE 2 — RESOURCES")

        # ── List all available resources ──────────────────────────
        subsection("resources/list — discover all resources")
        resources = await client.list_resources()
        for r in resources:
            print(f"  URI      : {r.uri}")
            print(f"  Name     : {r.name}")
            print(f"  Desc     : {r.description}")
            print()

        # ── Read static resource ──────────────────────────────────────
        subsection("resources/read — static: config://app/settings")
        # client.read_resource() returns list[TextResourceContents]
        # Each item has: .uri, .text (for text), .mimeType
        # NOTE: This is different from ctx.read_resource() inside a tool,
        #       which returns a ResourceResult with .contents[0].content
        contents = await client.read_resource("config://app/settings")
        import json
        config = json.loads(contents[0].text)
        print(f"  app_name    : {config['app_name']}")
        print(f"  environment : {config['environment']}")
        print(f"  generated_at: {config['generated_at']}")

        # ── Read dynamic resource (URI template) ──────────────────────
        subsection("resources/read — dynamic: users://{user_id}/profile")
        for user_id in ["1", "2", "3"]:
            contents = await client.read_resource(f"users://{user_id}/profile")
            profile = json.loads(contents[0].text)  # .text on TextResourceContents
            print(f"  [{user_id}] {profile['name']:10} | {profile['role']:10} | team: {profile['team']}")

        # ── Resource not found ────────────────────────────────────
        subsection("resources/read — user 99 (not found → error)")
        try:
            await client.read_resource("users://99/profile")
        except Exception as e:
            print(f"  ✓ Caught: {type(e).__name__}: {e}")

        # ── Read log resource ─────────────────────────────────────────
        subsection("resources/read — logs://app/recent")
        contents = await client.read_resource("logs://app/recent")
        logs = json.loads(contents[0].text)  # .text on TextResourceContents
        print(f"  {len(logs)} log entries:")
        for entry in logs:
            print(f"  [{entry['level']:5}] {entry['ts']} — {entry['msg']}")

        # ══════════════════════════════════════════════════════════
        # PRIMITIVE 3: PROMPTS
        # ══════════════════════════════════════════════════════════
        section("PRIMITIVE 3 — PROMPTS")

        # ── List all available prompts ────────────────────────────
        subsection("prompts/list — discover all prompts")
        prompts = await client.list_prompts()
        for p in prompts:
            print(f"  Name : {p.name}")
            print(f"  Desc : {p.description}")
            args = [f"{a.name}{'?' if not a.required else ''}" for a in (p.arguments or [])]
            print(f"  Args : {', '.join(args)}")
            print()

        # ── Get a simple prompt ───────────────────────────────────
        subsection("prompts/get — analyze_cost")
        result = await client.get_prompt("analyze_cost", {
            "service_name": "payment-api",
            "budget_usd": 2500.0
        })
        # result.messages is a list of PromptMessage objects
        print(f"  Messages returned: {len(result.messages)}")
        print(f"  Role    : {result.messages[0].role}")
        print(f"  Content preview:")
        preview = str(result.messages[0].content)[:200]
        print(f"    {preview}...")

        # ── Get a multi-turn prompt ───────────────────────────────
        subsection("prompts/get — debug_session (multi-turn)")
        result = await client.get_prompt("debug_session", {
            "error_message": "KeyError: 'user_id' in auth middleware",
            "language": "Python"
        })
        print(f"  Messages returned: {len(result.messages)}")
        for i, msg in enumerate(result.messages):
            preview = str(msg.content)[:120].replace('\n', ' ')
            print(f"  [{i}] role={msg.role} | {preview}...")

        # ── Get incident response prompt ──────────────────────────
        subsection("prompts/get — aws_incident_response (critical)")
        result = await client.get_prompt("aws_incident_response", {
            "service": "RDS",
            "severity": "critical"
        })
        print(f"  Messages returned: {len(result.messages)}")
        preview = str(result.messages[0].content)[:300].replace('\n', ' ')
        print(f"  Content preview: {preview}...")

    print(f"\n\n{'═' * 60}")
    print("  ALL PRIMITIVES EXERCISED")
    print(f"{'═' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
