# phase-02-jsonrpc/minimal_client.py
#
# PURPOSE: A bare-bones MCP client that talks to minimal_server.py over stdio.
# This simulates exactly what a Host (like Claude Desktop or LangGraph) does
# when it starts up a local MCP server.
#
# Run with:  python3 minimal_client.py
# (It will spawn the server itself as a subprocess)

import json
import subprocess
import sys

# ─────────────────────────────────────────────────────────────────────────────
# Spawn the server as a subprocess — this is the stdio transport model
# ─────────────────────────────────────────────────────────────────────────────

server_process = subprocess.Popen(
    [sys.executable, "minimal_server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=sys.stderr,          # Server's debug logs go to our terminal
    text=True,
    bufsize=1                   # Line-buffered
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_id_counter = 0

def next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter

def send_request(method: str, params: dict = None) -> dict:
    """Send a JSON-RPC request and wait for the matching response."""
    req_id = next_id()
    msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params:
        msg["params"] = params

    line = json.dumps(msg) + "\n"
    print(f"\n[CLIENT → SERVER] {line.strip()}")
    server_process.stdin.write(line)
    server_process.stdin.flush()

    # Read back the response
    response_line = server_process.stdout.readline()
    response = json.loads(response_line.strip())
    print(f"[SERVER → CLIENT] {json.dumps(response, indent=2)}")
    return response

def send_notification(method: str, params: dict = None):
    """Send a JSON-RPC notification (no id, no response expected)."""
    msg = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    line = json.dumps(msg) + "\n"
    print(f"\n[CLIENT → SERVER] {line.strip()} (notification — no response)")
    server_process.stdin.write(line)
    server_process.stdin.flush()

# ─────────────────────────────────────────────────────────────────────────────
# The MCP session — step by step
# ─────────────────────────────────────────────────────────────────────────────

def run_session():
    print("=" * 60)
    print("  MCP SESSION — Raw JSON-RPC over stdio")
    print("=" * 60)

    # ── Step 1: Handshake ────────────────────────────────────────────────────
    print("\n\n── STEP 1: initialize (handshake) ──────────────────────────")
    init_response = send_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {"sampling": {}},
        "clientInfo": {"name": "minimal-client", "version": "0.0.1"}
    })
    server_name = init_response["result"]["serverInfo"]["name"]
    print(f"\n  ✓ Connected to server: '{server_name}'")

    # ── Step 2: Send initialized notification ────────────────────────────────
    print("\n── STEP 2: notifications/initialized (complete handshake) ──")
    send_notification("notifications/initialized")

    # ── Step 3: Discover tools ───────────────────────────────────────────────
    print("\n── STEP 3: tools/list (discover available tools) ───────────")
    tools_response = send_request("tools/list")
    tools = tools_response["result"]["tools"]
    print(f"\n  ✓ Server has {len(tools)} tool(s):")
    for t in tools:
        print(f"    • {t['name']}: {t['description']}")

    # ── Step 4: Call a tool ──────────────────────────────────────────────────
    print("\n── STEP 4: tools/call — calling 'greet' ────────────────────")
    greet_response = send_request("tools/call", {
        "name": "greet",
        "arguments": {"name": "Darshan"}
    })
    content = greet_response["result"]["content"][0]["text"]
    print(f"\n  ✓ Tool result: {content}")

    # ── Step 5: Call another tool ────────────────────────────────────────────
    print("\n── STEP 5: tools/call — calling 'add' ──────────────────────")
    add_response = send_request("tools/call", {
        "name": "add",
        "arguments": {"a": 17, "b": 25}
    })
    content = add_response["result"]["content"][0]["text"]
    print(f"\n  ✓ Tool result: {content}")

    # ── Step 6: Call a non-existent tool ────────────────────────────────────
    print("\n── STEP 6: tools/call — calling a MISSING tool (error) ─────")
    bad_response = send_request("tools/call", {
        "name": "fly_to_moon",
        "arguments": {}
    })
    if "error" in bad_response:
        err = bad_response["error"]
        print(f"\n  ✓ Got expected error: code={err['code']}, message='{err['message']}'")

    print("\n\n" + "=" * 60)
    print("  SESSION COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    try:
        run_session()
    finally:
        server_process.stdin.close()
        server_process.wait()
