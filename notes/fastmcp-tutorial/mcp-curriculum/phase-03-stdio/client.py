# phase-03-stdio/client.py
#
# PURPOSE: Use FastMCP's built-in Client to talk to our server.
# FastMCP 3.x returns a CallToolResult object (not a list).
# Key attributes:
#   result.data          → the raw Python value (str, int, dict...)
#   result.content       → list of ContentBlock objects (text, image, etc.)
#   result.content[0].text → the text of the first content block
#   result.is_error      → True if the tool raised an exception
#
# Run with: uv run python phase-03-stdio/client.py

import asyncio
from pathlib import Path
from fastmcp import Client

# Absolute path so this works regardless of which directory you run from
SERVER_PATH = Path(__file__).parent / "server.py"


async def main():
    print("=" * 60)
    print("  FastMCP Client — Phase 03")
    print("=" * 60)

    # async with Client(...) spawns the server, runs the handshake,
    # keeps the connection alive, and shuts down cleanly on exit.
    async with Client(SERVER_PATH) as client:

        # ── 1. List available tools ──────────────────────────────────────────
        print("\n── Available Tools ─────────────────────────────────────────")
        tools = await client.list_tools()
        for tool in tools:
            print(f"\n  Tool   : {tool.name}")
            print(f"  Desc   : {tool.description}")
            print(f"  Schema : {tool.inputSchema}")

        # ── 2. greet ─────────────────────────────────────────────────────────
        print("\n\n── Calling: greet ──────────────────────────────────────────")
        result = await client.call_tool("greet", {"name": "Darshan"})
        # result.data is the plain Python value FastMCP extracted
        print(f"  result.data        = {result.data!r}")
        print(f"  result.is_error    = {result.is_error}")
        print(f"  result.content[0]  = {result.content[0]}")

        # ── 3. add ───────────────────────────────────────────────────────────
        print("\n── Calling: add ────────────────────────────────────────────")
        result = await client.call_tool("add", {"a": 17, "b": 25})
        print(f"  Result: {result.data}")

        # ── 4. divide (normal) ───────────────────────────────────────────────
        print("\n── Calling: divide (10 / 4) ────────────────────────────────")
        result = await client.call_tool("divide", {"numerator": 10, "denominator": 4})
        print(f"  Result: {result.data}")

        # ── 5. divide (by zero) — FastMCP raises ToolError client-side ───────
        print("\n── Calling: divide (10 / 0) — expect ToolError ─────────────")
        try:
            result = await client.call_tool("divide", {"numerator": 10, "denominator": 0})
            print(f"  Result: {result.data}")
        except Exception as e:
            # FastMCP raises an exception on the client when isError=true
            print(f"  ✓ Caught: {type(e).__name__}: {e}")

        # ── 6. describe_person (nested Pydantic → nested JSON object) ────────
        print("\n── Calling: describe_person ────────────────────────────────")
        result = await client.call_tool("describe_person", {
            "person": {"name": "Darshan", "age": 28, "role": "software engineer"}
        })
        print(f"  Result: {result.data}")

    print("\n\n" + "=" * 60)
    print("  SESSION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
