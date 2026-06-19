# Phase 4 — FastMCP Primitives Deep Dive

> **Reference guide for all four MCP primitives: Tools, Resources, Prompts, and Context. Return here when you need a complete API reference for any primitive.**

---

## What You Built

| File | Purpose |
|---|---|
| `server.py` | One server demonstrating all four primitives together |
| `client.py` | Client that exercises every primitive with annotated output |

Run it: `uv run python phase-04-primitives/client.py`

---

## The Four Primitives — Quick Reference

| Primitive | Decorator | Controlled by | Purpose |
|---|---|---|---|
| **Tool** | `@mcp.tool()` | LLM (model) | Actions with side effects — runs code |
| **Resource** | `@mcp.resource(uri)` | App / User | Read-only data addressed by URI |
| **Prompt** | `@mcp.prompt()` | User | Reusable message templates for LLMs |
| **Context** | Injected by FastMCP | Your code | Logging, progress, cross-primitive calls |

---

## PRIMITIVE 1 — Tools

### Basic Patterns

```python
# Sync tool
@mcp.tool()
def my_tool(x: str) -> str:
    """Description the LLM reads."""
    return f"result: {x}"

# Async tool (use whenever doing I/O — boto3, httpx, DB queries)
@mcp.tool()
async def my_async_tool(x: str) -> str:
    result = await some_io_operation(x)
    return result

# Tool with Context (logging + progress)
@mcp.tool()
async def my_tool_with_context(x: str, ctx: Context) -> str:
    await ctx.info("Starting...")      # log to client
    await ctx.report_progress(1, 3)   # progress notification
    result = await do_work(x)
    await ctx.report_progress(3, 3)
    return result
```

### Return Types

| Return type | What the LLM sees |
|---|---|
| `str` | Plain text content block |
| `int` / `float` | Stringified number |
| `dict` / `list` | JSON-serialized text + `structured_content` |
| Pydantic model | JSON-serialized text + `structured_content` |

### Error Handling

```python
@mcp.tool()
def risky_tool(value: int) -> str:
    if value < 0:
        raise ValueError("Value must be non-negative")  # → isError: true
    return str(value * 2)
```

Client side:
```python
try:
    result = await client.call_tool("risky_tool", {"value": -1})
except Exception as e:  # FastMCP raises ToolError
    print(f"Tool failed: {e}")
```

---

## PRIMITIVE 2 — Resources

Resources are read-only data sources addressed by URIs. Think of them as the server's file system or database, exposed to clients.

### Static URI
```python
@mcp.resource("config://app/settings")
def get_settings() -> str:
    """Return app settings as JSON."""
    return json.dumps({"version": "1.0", "env": "production"})
```

### Dynamic URI Template
```python
@mcp.resource("users://{user_id}/profile")
def get_user(user_id: str) -> str:
    """Return a user profile by ID."""
    # URI: users://42/profile → user_id = "42"
    user = db.get(user_id)
    if not user:
        raise ValueError(f"User {user_id!r} not found")
    return json.dumps(user)
```

### URI Naming Conventions

| Pattern | Use for |
|---|---|
| `config://app/...` | Application configuration |
| `db://table/id` | Database records |
| `file:///path/to/file` | File contents |
| `logs://service/recent` | Log streams |
| `{service}://{id}/...` | Any domain-specific namespace |

### Resource Return Types

```python
# Text (most common)
@mcp.resource("data://text")
def text_resource() -> str:
    return "plain text or JSON string"

# Binary
@mcp.resource("data://image")
def binary_resource() -> bytes:
    with open("image.png", "rb") as f:
        return f.read()  # mimeType detected automatically
```

### Important: URI Templates Don't Appear in `resources/list`

Only **concrete** (non-template) URIs appear in `resources/list`. URI templates must be discovered through documentation or prompts. The client calls `resources/read` with the fully resolved URI:
```python
# Resolving a template manually:
contents = await client.read_resource("users://42/profile")
```

---

## PRIMITIVE 3 — Prompts

Prompts are reusable message templates exposed by the server. The user (or host application) selects them; they return messages ready to send to an LLM.

### Single-message Prompt (return str)
```python
@mcp.prompt()
def analyze_cost(service: str, budget: float) -> str:
    """Generate a cost analysis prompt."""
    return (
        f"Analyze cloud costs for '{service}'. "
        f"Budget: ${budget:.2f}/month. "
        f"Suggest 3 optimizations."
    )
```

### Multi-turn Prompt (return list[Message])
```python
from fastmcp.prompts import Message

@mcp.prompt()
def debug_session(error: str, lang: str = "Python") -> list[Message]:
    """Set up a debugging conversation."""
    return [
        Message(
            role="user",
            content=f"I got this {lang} error: {error}. Help me fix it."
        )
    ]
```

### Client Usage
```python
# List available prompts
prompts = await client.list_prompts()
# prompt.name, prompt.description, prompt.arguments

# Render a prompt
result = await client.get_prompt("debug_session", {
    "error": "KeyError: 'user_id'",
    "lang": "Python"
})
# result.messages is list[PromptMessage]
# result.messages[0].role    → "user" or "assistant"
# result.messages[0].content → the text content
```

### Optional Arguments
Arguments with defaults are optional (`?` suffix when listed):
```python
def my_prompt(required_arg: str, optional_arg: str = "default") -> str:
    ...
# Args: required_arg, optional_arg?
```

---

## PRIMITIVE 4 — Context

`Context` is injected automatically by FastMCP when it appears as a type-annotated parameter. **You never pass it yourself.**

### Injection
```python
from fastmcp import Context

@mcp.tool()
async def my_tool(name: str, ctx: Context) -> str:  # ctx injected automatically
    ...
```

### Full Context API

```python
# Logging (sends notifications/message to client)
await ctx.debug("Detailed debug info")
await ctx.info("Processing started")
await ctx.warning("Slow response detected")
await ctx.error("Something went wrong")

# Progress notifications (sends notifications/progress)
await ctx.report_progress(current=3, total=10)
# Client sees: {"progress": 3, "total": 10}

# Read a resource from within a tool
# Returns ResourceResult — NOT the same as client.read_resource()
result = await ctx.read_resource("config://app/settings")
text = result.contents[0].content  # .content not .text here!

# Request metadata
print(ctx.request_id)   # current request's ID
print(ctx.client_id)    # connected client's ID
print(ctx.session_id)   # session ID
```

---

## ⚠️ FastMCP 3.x API Gotcha: Resource Return Types

This is the most common source of bugs — **two different shapes depending on where you read from**:

| Called from | Returns | Access text via |
|---|---|---|
| `client.read_resource(uri)` | `list[TextResourceContents]` | `contents[0].text` |
| `ctx.read_resource(uri)` (inside tool) | `ResourceResult` | `result.contents[0].content` |

```python
# From the CLIENT:
contents = await client.read_resource("config://app/settings")
text = contents[0].text  # TextResourceContents.text

# From INSIDE A TOOL (via ctx):
result = await ctx.read_resource("config://app/settings")
text = result.contents[0].content  # ResourceResult.contents[0].content
```

Same data, two different wrapper types. Always check which context you're in.

---

## Cross-Primitive Usage

Primitives can call each other. The most useful pattern: **a Tool reads a Resource**.

```python
@mcp.resource("config://db")
def get_db_config() -> str:
    return json.dumps({"host": "localhost", "port": 5432})

@mcp.tool()
async def connect_db(ctx: Context) -> str:
    """Connect to the database using stored config."""
    resource = await ctx.read_resource("config://db")
    config = json.loads(resource.contents[0].content)
    # now connect using config["host"], config["port"]
    return f"Connected to {config['host']}:{config['port']}"
```

---

## CallToolResult — Full Reference (FastMCP 3.x)

```python
result = await client.call_tool("my_tool", {"arg": "value"})

result.data               # Plain Python value (str, dict, list, etc.)
result.is_error           # True if tool raised an exception
result.content            # list[ContentBlock] — the MCP content array
result.content[0].text    # Text of the first content block
result.structured_content # Parsed dict/list if tool returned JSON
result.meta               # FastMCP metadata
```

---

## Complete Server Template

```python
import sys, json, logging, asyncio
from fastmcp import FastMCP, Context
from fastmcp.prompts import Message
from pydantic import BaseModel, Field

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
mcp = FastMCP("my-server")

# TOOL
@mcp.tool()
async def my_tool(name: str, ctx: Context) -> dict:
    """What this tool does."""
    await ctx.info(f"Processing {name}")
    return {"result": name.upper()}

# RESOURCE (static)
@mcp.resource("config://my/data")
def my_data() -> str:
    return json.dumps({"key": "value"})

# RESOURCE (dynamic)
@mcp.resource("items://{item_id}")
def get_item(item_id: str) -> str:
    return json.dumps({"id": item_id, "name": f"Item {item_id}"})

# PROMPT
@mcp.prompt()
def my_prompt(topic: str) -> str:
    """Generate a prompt about a topic."""
    return f"Explain {topic} in detail."

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## Key Takeaways

1. **Tools** = actions. **Resources** = data. **Prompts** = templates. **Context** = server-side utilities.
2. `ctx` is injected automatically — just type-annotate it and FastMCP handles the rest.
3. `ctx.info()`, `ctx.report_progress()` send live notifications the host UI can display.
4. URI templates (`{param}`) make one resource handler serve many URIs — like URL routing.
5. URI templates **don't appear in `resources/list`** — only concrete URIs do.
6. `client.read_resource()` → `list[TextResourceContents]` with `.text`.
7. `ctx.read_resource()` → `ResourceResult` with `.contents[0].content`. Different shapes!
8. Tool errors: `raise` = `isError: true` (LLM sees message). Return = `isError: false`.
9. Prompts: return `str` for single message, `list[Message]` for multi-turn conversations.
