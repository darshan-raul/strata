# phase-02-jsonrpc/minimal_server.py
#
# PURPOSE: The world's simplest MCP server — no FastMCP, no abstraction.
# We're implementing just enough JSON-RPC 2.0 to handle an MCP handshake
# and respond to a tools/list call. Read every line carefully.
#
# Run with:  python3 minimal_server.py
# Talk to it: python3 minimal_client.py

import json
import sys

# ─────────────────────────────────────────────────────────────────────────────
# Helpers: read/write newline-delimited JSON on stdio
# ─────────────────────────────────────────────────────────────────────────────

def send(msg: dict):
    """Serialize msg to JSON and write it to stdout (the transport)."""
    line = json.dumps(msg)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()
    # We write to stderr so we can observe what's going out (stderr is visible)
    print(f"[SERVER → CLIENT] {line}", file=sys.stderr)

def receive() -> dict | None:
    """Read one line from stdin, parse it as JSON."""
    line = sys.stdin.readline()
    if not line:
        return None
    msg = json.loads(line.strip())
    print(f"[CLIENT → SERVER] {json.dumps(msg)}", file=sys.stderr)
    return msg

# ─────────────────────────────────────────────────────────────────────────────
# Message builders — pure JSON-RPC 2.0 spec
# ─────────────────────────────────────────────────────────────────────────────

def make_response(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}

def make_error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

def make_notification(method: str, params: dict = None) -> dict:
    msg = {"jsonrpc": "2.0", "method": method}
    if params:
        msg["params"] = params
    return msg

# ─────────────────────────────────────────────────────────────────────────────
# Method handlers — one function per JSON-RPC method
# ─────────────────────────────────────────────────────────────────────────────

def handle_initialize(req_id, params):
    """
    MCP handshake step 1: client says hello, server responds with capabilities.
    Notice we're negotiating the protocol version and advertising what we support.
    """
    client_version = params.get("protocolVersion", "unknown")
    client_name = params.get("clientInfo", {}).get("name", "unknown")
    print(f"[SERVER] Client '{client_name}' connecting with protocol v{client_version}", file=sys.stderr)

    return make_response(req_id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            # We tell the client: yes, we have tools. No dynamic list changes.
            "tools": {"listChanged": False},
        },
        "serverInfo": {
            "name": "minimal-mcp-server",
            "version": "0.0.1"
        }
    })

def handle_tools_list(req_id):
    """
    Client is asking: "what tools do you have?"
    We return a list of tool definitions. Each tool has:
    - name: the method name the client will use in tools/call
    - description: what the LLM reads to decide when to use this tool
    - inputSchema: JSON Schema describing the arguments
    """
    return make_response(req_id, {
        "tools": [
            {
                "name": "greet",
                "description": "Say hello to a person by name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "The person's name"
                        }
                    },
                    "required": ["name"]
                }
            },
            {
                "name": "add",
                "description": "Add two numbers together",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"}
                    },
                    "required": ["a", "b"]
                }
            }
        ]
    })

def handle_tools_call(req_id, params):
    """
    Client is calling a tool by name with arguments.
    We route to the right function and return a content array.
    
    MCP tool results are always a list of content blocks.
    Each block has a 'type' — we use 'text' here (images, audio also exist).
    """
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name == "greet":
        person = arguments.get("name", "stranger")
        result_text = f"Hello, {person}! Welcome to MCP."
        return make_response(req_id, {
            "content": [{"type": "text", "text": result_text}],
            "isError": False
        })

    elif tool_name == "add":
        a = arguments.get("a", 0)
        b = arguments.get("b", 0)
        result_text = f"{a} + {b} = {a + b}"
        return make_response(req_id, {
            "content": [{"type": "text", "text": result_text}],
            "isError": False
        })

    else:
        # Tool not found — use JSON-RPC error code -32601
        return make_error(req_id, -32601, f"Tool not found: {tool_name}")

# ─────────────────────────────────────────────────────────────────────────────
# Main loop — read messages, dispatch, respond
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("[SERVER] Starting minimal MCP server on stdio...", file=sys.stderr)

    while True:
        msg = receive()
        if msg is None:
            print("[SERVER] stdin closed, shutting down.", file=sys.stderr)
            break

        method = msg.get("method")
        req_id = msg.get("id")          # None for notifications
        params = msg.get("params", {})

        # ── Dispatch table ──────────────────────────────────────────────────
        if method == "initialize":
            send(handle_initialize(req_id, params))

        elif method == "notifications/initialized":
            # This is a notification — no response needed, no id
            print("[SERVER] Handshake complete. Ready for tool calls.", file=sys.stderr)

        elif method == "tools/list":
            send(handle_tools_list(req_id))

        elif method == "tools/call":
            send(handle_tools_call(req_id, params))

        elif method == "ping":
            # Optional but useful for health checks
            send(make_response(req_id, {}))

        else:
            if req_id is not None:
                # Only send an error response if it was a request (has id)
                send(make_error(req_id, -32601, f"Method not found: {method}"))

if __name__ == "__main__":
    main()
