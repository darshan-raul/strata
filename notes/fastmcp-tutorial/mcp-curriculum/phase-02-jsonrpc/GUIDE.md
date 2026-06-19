# Phase 2 — JSON-RPC Under the Hood

> **Reference guide for the MCP wire protocol. Come back here whenever you're debugging a server or want to understand what's happening beneath any MCP abstraction.**

---

## What You Built

| File | Purpose |
|---|---|
| `minimal_server.py` | A hand-written MCP server in raw JSON-RPC — no FastMCP |
| `minimal_client.py` | A client that spawns the server as a subprocess and runs a full MCP session |

Run it: `python3 minimal_client.py`

---

## Core Concept: JSON-RPC 2.0

MCP is built on **JSON-RPC 2.0** — a lightweight protocol for remote procedure calls encoded as JSON. Every message is a plain JSON object, one per line, sent over a transport (stdio or HTTP/SSE).

### The Three Message Types

#### 1. Request (expects a response)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "greet",
    "arguments": { "name": "Darshan" }
  }
}
```
- `id`: Required. Any string or int. **Matched back in the response** so the client knows which reply belongs to which request.
- `method`: The operation to invoke.
- `params`: Arguments (optional).

#### 2. Response (success)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{ "type": "text", "text": "Hello, Darshan!" }],
    "isError": false
  }
}
```

#### 2b. Response (error)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32601,
    "message": "Tool not found: fly_to_moon"
  }
}
```
A response always has **either** `result` or `error` — never both, never neither.

#### 3. Notification (fire-and-forget, no response)
```json
{
  "jsonrpc": "2.0",
  "method": "notifications/initialized"
}
```
No `id` field. Recipient never replies.

### Standard Error Codes

| Code | Meaning |
|---|---|
| `-32700` | Parse error (invalid JSON) |
| `-32600` | Invalid Request |
| `-32601` | Method not found |
| `-32602` | Invalid params |
| `-32603` | Internal error |
| `-32000` to `-32099` | Server-defined errors |

---

## The MCP Handshake (3 Steps)

Every MCP connection starts with this exact sequence before any tools can be called:

```
Step 1: CLIENT → SERVER
  { "jsonrpc":"2.0", "id":1, "method":"initialize",
    "params": { "protocolVersion": "2024-11-05",
                "capabilities": { "sampling": {} },
                "clientInfo": { "name": "my-client", "version": "0.1" } } }

Step 2: SERVER → CLIENT
  { "jsonrpc":"2.0", "id":1,
    "result": { "protocolVersion": "2024-11-05",
                "capabilities": { "tools": { "listChanged": false } },
                "serverInfo": { "name": "my-server", "version": "1.0" } } }

Step 3: CLIENT → SERVER  (notification — no id, no response)
  { "jsonrpc":"2.0", "method": "notifications/initialized" }
```

Only after step 3 can tool calls be made.

---

## Full MCP Method Reference

| Method | Direction | Description |
|---|---|---|
| `initialize` | C→S | Handshake step 1 |
| `notifications/initialized` | C→S | Handshake step 3 (notification) |
| `tools/list` | C→S | Discover available tools |
| `tools/call` | C→S | Invoke a tool |
| `resources/list` | C→S | Discover available resources |
| `resources/read` | C→S | Read a resource by URI |
| `prompts/list` | C→S | Discover available prompts |
| `prompts/get` | C→S | Render a prompt with arguments |
| `ping` | C→S | Health check |
| `notifications/progress` | S→C | Progress update from a tool |
| `notifications/message` | S→C | Log message from the server |

---

## Tool Calls: Request and Response Shape

### Request
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "add",
    "arguments": { "a": 17, "b": 25 }
  }
}
```

### Success Response
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [{ "type": "text", "text": "17 + 25 = 42" }],
    "isError": false
  }
}
```

### Error Response (application-level — tool raised an exception)
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [{ "type": "text", "text": "Cannot divide by zero." }],
    "isError": true
  }
}
```

> ⚠️ **Critical distinction**: A tool error is still a **successful JSON-RPC response** (`result`, not `error`). The `isError: true` flag is inside `result`. This is intentional — the LLM reads the error text and decides what to do (retry, rephrase, give up). A JSON-RPC-level `error` means the protocol itself failed (bad method name, bad JSON, etc.).

---

## The inputSchema: What the LLM Reads

When the client calls `tools/list`, each tool includes an `inputSchema` — a **JSON Schema** object describing the arguments the tool accepts. The LLM reads this to know how to construct a valid `tools/call`.

```json
{
  "name": "add",
  "description": "Add two numbers together",
  "inputSchema": {
    "type": "object",
    "properties": {
      "a": { "type": "number", "description": "First number" },
      "b": { "type": "number", "description": "Second number" }
    },
    "required": ["a", "b"]
  }
}
```

In Phase 3, FastMCP generates this schema automatically from your Python type hints.

---

## The Two Transports

### stdio Transport
```
Host Process
  ├── stdout ──→ Server's stdin   (host sends JSON-RPC messages)
  └── stdin  ←── Server's stdout  (server sends JSON-RPC messages)
```
- Host **spawns the server as a subprocess** with `subprocess.Popen()`
- Messages are **newline-delimited JSON** on stdin/stdout
- One client per server process
- Used by: Claude Desktop, local tool integrations
- Server is started and killed by the host

### SSE Transport (HTTP + Server-Sent Events)
```
Client                        Server (HTTP)
  ├── GET /sse ─────────────→ (opens persistent event stream)
  │←── event: endpoint ──────  (server tells client where to POST)
  ├── POST /messages/ ───────→ (client sends JSON-RPC requests)
  │←── event: message ───────  (server sends responses via SSE)
```
- Server runs **independently** as an HTTP server
- Multiple clients can connect simultaneously
- Works over a network
- Used by: remote servers, LangGraph agents, shared services

### When to Use Which

| Scenario | Transport |
|---|---|
| Local tool on same machine | stdio |
| Claude Desktop integration | stdio |
| Server is remote / in the cloud | SSE |
| Multiple clients share one server | SSE |
| Server has expensive startup (loads ML model) | SSE |
| Running as a persistent service (Docker/systemd) | SSE |

---

## The stdout Rule (Critical)

In stdio transport, **stdout IS the protocol wire**. The client reads it expecting only newline-delimited JSON.

```python
# ❌ WRONG — corrupts the JSON-RPC stream
print("Server started!")
print(f"Processing: {value}")

# ✅ CORRECT — debug goes to stderr, never touches the wire
print("Server started!", file=sys.stderr)
print(f"Processing: {value}", file=sys.stderr)

# ✅ BEST — use logging configured to stderr
import logging, sys
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("Server started!")  # safe
```

This is why `subprocess.Popen()` separates `stdout=subprocess.PIPE` (JSON, captured) from `stderr=sys.stderr` (logs, shown in terminal).

---

## Subprocess Spawning — Real Production Pattern

The `subprocess.Popen()` approach used in `minimal_client.py` is **exactly how Claude Desktop works**:

```json
// ~/.config/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "my-aws-server": {
      "command": "python3",
      "args": ["/path/to/server.py"]
    }
  }
}
```

Claude Desktop literally spawns a subprocess per server entry, connects stdin/stdout pipes, runs the handshake, and calls tools. FastMCP's `Client` does the same thing when you pass it a `.py` file path.

---

## Key Takeaways

1. **Every MCP message is JSON-RPC 2.0** — one JSON object per line.
2. **Requests have `id`; notifications don't.** Responses echo back the `id`.
3. **The 3-step handshake must complete** before any tool calls.
4. **Tool errors ≠ JSON-RPC errors.** Tool errors live inside `result` with `isError: true`.
5. **stdout is sacred in stdio transport.** Only JSON goes there. Logs go to stderr.
6. **Subprocess spawning is real production practice**, not a tutorial shortcut.
7. **JSON Schema in `inputSchema`** is what LLMs read to know how to call your tools — write good descriptions.
