# phase-03-stdio/inspect_schema.py
#
# PURPOSE: Prove that FastMCP is generating the same JSON-RPC messages
# we wrote by hand in Phase 2. This sends raw JSON to the FastMCP server
# and prints what comes back — no abstraction.
#
# This is useful for:
#   - Debugging a server's actual wire output
#   - Verifying schema generation from type hints
#   - Understanding what an LLM actually sees when it reads tool definitions
#
# Run with: python3 inspect_schema.py

import json
import subprocess
import sys

# Spawn the FastMCP server (exactly like Phase 2)
server = subprocess.Popen(
    [sys.executable, "server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,  # suppress server's debug logs for clean output
    text=True,
    bufsize=1,
)

def send_raw(msg: dict) -> dict:
    line = json.dumps(msg) + "\n"
    server.stdin.write(line)
    server.stdin.flush()
    response_line = server.stdout.readline()
    return json.loads(response_line.strip())

def send_notif(msg: dict):
    server.stdin.write(json.dumps(msg) + "\n")
    server.stdin.flush()

print("=" * 70)
print("  RAW WIRE INSPECTION — FastMCP server (phase-03-stdio/server.py)")
print("=" * 70)

# ── Handshake ────────────────────────────────────────────────────────────────
init_resp = send_raw({
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "inspector", "version": "0.1"}
    }
})
send_notif({"jsonrpc": "2.0", "method": "notifications/initialized"})

print(f"\n✓ Server name : {init_resp['result']['serverInfo']['name']}")
print(f"✓ Protocol    : {init_resp['result']['protocolVersion']}")
print(f"✓ Capabilities: {list(init_resp['result']['capabilities'].keys())}")

# ── tools/list — look at the generated schemas ───────────────────────────────
tools_resp = send_raw({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
tools = tools_resp["result"]["tools"]

print(f"\n\n── tools/list → {len(tools)} tools discovered ─────────────────────────────")
for tool in tools:
    print(f"\n  ┌─ Tool: {tool['name']}")
    print(f"  │  Description: {tool['description']}")
    print(f"  │  Input Schema:")
    schema_str = json.dumps(tool["inputSchema"], indent=4)
    for line in schema_str.splitlines():
        print(f"  │    {line}")
    print(f"  └{'─' * 50}")

# ── tools/call — raw success response ───────────────────────────────────────
print("\n\n── tools/call greet — raw response ─────────────────────────────────────")
greet_resp = send_raw({
    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
    "params": {"name": "greet", "arguments": {"name": "Darshan"}}
})
print(json.dumps(greet_resp, indent=2))

# ── tools/call — raw error response (divide by zero) ────────────────────────
print("\n── tools/call divide/0 — raw error response ─────────────────────────────")
div_resp = send_raw({
    "jsonrpc": "2.0", "id": 4, "method": "tools/call",
    "params": {"name": "divide", "arguments": {"numerator": 10, "denominator": 0}}
})
print(json.dumps(div_resp, indent=2))

# ── tools/call — Pydantic nested object ─────────────────────────────────────
print("\n── tools/call describe_person — nested Pydantic object ─────────────────")
person_resp = send_raw({
    "jsonrpc": "2.0", "id": 5, "method": "tools/call",
    "params": {
        "name": "describe_person",
        "arguments": {
            "person": {"name": "Darshan", "age": 28, "role": "software engineer"}
        }
    }
})
print(json.dumps(person_resp, indent=2))

server.stdin.close()
server.wait()
print("\n✓ Done.")
