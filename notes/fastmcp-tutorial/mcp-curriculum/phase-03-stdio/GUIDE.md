# Phase 3 — Your First FastMCP Server (stdio)

> **Reference guide for building FastMCP servers over stdio. The contrast with Phase 2's manual approach shows exactly what the framework abstracts.**

---

## What You Built

| File | Purpose |
|---|---|
| `server.py` | A FastMCP server with 4 tools, replacing 150 lines of Phase 2 with ~60 lines |
| `client.py` | FastMCP `Client` that spawns the server and calls all tools |
| `inspect_schema.py` | Raw JSON-RPC inspector — proves FastMCP speaks the same protocol |

Run it: `uv run python phase-03-stdio/client.py`

---

## The Core Abstraction

Everything you wrote manually in Phase 2 (`handle_initialize`, `handle_tools_list`, `handle_tools_call`, the stdin/stdout loop, JSON serialization) is replaced by:

```python
from fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def my_tool(arg: str) -> str:
    """Tool description."""
    return f"Result: {arg}"

mcp.run(transport="stdio")
```

`FastMCP` handles:
- Protocol negotiation (initialize handshake)
- Schema generation from type hints
- Method dispatch (tools/list, tools/call routing)
- stdout/stderr separation
- Error serialization (Python exceptions → `isError: true`)
- Transport setup (stdin/stdout event loop)

---

## Type Hint → JSON Schema Mapping

FastMCP reads your function signatures and generates `inputSchema` automatically:

| Python Type | JSON Schema type |
|---|---|
| `str` | `"string"` |
| `int` | `"integer"` |
| `float` | `"number"` |
| `bool` | `"boolean"` |
| `list` | `"array"` |
| `dict` | `"object"` |
| `None` / `Optional[X]` | adds to `not required` |
| Pydantic `BaseModel` | nested `"object"` with full sub-schema |

### Example
```python
@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers together."""
    return f"{a} + {b} = {a + b}"
```
Generates:
```json
{
  "type": "object",
  "properties": {
    "a": { "type": "number" },
    "b": { "type": "number" }
  },
  "required": ["a", "b"],
  "additionalProperties": false
}
```

---

## Error Handling: Two Approaches

There are two ways errors surface in MCP — and they mean different things:

### Approach A: Raise a Python exception (application error)
```python
@mcp.tool()
def divide(numerator: float, denominator: float) -> str:
    if denominator == 0:
        raise ValueError("Cannot divide by zero.")  # ← raise anything
    return str(numerator / denominator)
```

Wire output:
```json
{ "result": { "content": [{"type":"text", "text": "Error calling tool 'divide': Cannot divide by zero."}], "isError": true } }
```

- **Use when**: Expected domain errors (bad input, resource not found, business logic violation)
- **Effect**: The LLM **sees the error message** and can decide to retry, rephrase, or inform the user
- **Client side**: FastMCP raises `ToolError` — catch with `except Exception`

### Approach B: Return normally
```python
@mcp.tool()
def safe_divide(a: float, b: float) -> str:
    if b == 0:
        return "Cannot divide by zero — please provide a non-zero denominator."
    return str(a / b)
```

- **Use when**: You want the LLM to receive a graceful message as if it were a normal result
- **Effect**: `isError: false` — the LLM treats this as a successful response

> **Rule of thumb**: `raise` for invalid inputs/unexpected states. `return` error messages for expected negative outcomes the LLM should handle gracefully.

---

## Pydantic Models as Tool Arguments

```python
from pydantic import BaseModel, Field

class Person(BaseModel):
    name: str = Field(description="The person's full name")
    age: int = Field(description="Age in years", ge=0, le=150)
    role: str = Field(default="engineer", description="Job role")

@mcp.tool()
def describe_person(person: Person) -> str:
    """Generate a description from a person's profile."""
    return f"{person.name} is a {person.age}-year-old {person.role}."
```

Generated schema (nested object):
```json
{
  "type": "object",
  "properties": {
    "person": {
      "type": "object",
      "properties": {
        "name": { "type": "string", "description": "The person's full name" },
        "age":  { "type": "integer", "minimum": 0, "maximum": 150 },
        "role": { "type": "string", "default": "engineer" }
      },
      "required": ["name", "age"]
    }
  },
  "required": ["person"]
}
```

The LLM sends: `{"person": {"name": "Darshan", "age": 28}}`
FastMCP validates and constructs the `Person` model for you.

`Field(ge=0, le=150)` → `minimum` / `maximum` in the schema. `Field(description=...)` → `description` in the schema. These appear in the LLM's tool definition and influence how the LLM fills arguments.

---

## FastMCP Client API (v3.x)

```python
from fastmcp import Client
from pathlib import Path

async with Client(Path("server.py")) as client:
    # List tools
    tools = await client.list_tools()
    # tool.name, tool.description, tool.inputSchema

    # Call a tool
    result = await client.call_tool("tool_name", {"arg": "value"})
    # result.data          → plain Python value (str, int, dict...)
    # result.content       → list of ContentBlock (text, image...)
    # result.content[0].text → the text content
    # result.is_error      → True if the tool raised an exception
    # result.structured_content → parsed JSON if tool returned dict/list
```

### Transport options for `Client()`

| Argument | Transport used | Example |
|---|---|---|
| `Path("server.py")` | stdio (spawns subprocess) | `Client(Path("server.py"))` |
| `"http://localhost:8000"` | SSE (connects to running server) | `Client("http://localhost:8000/sse")` |
| `FastMCP instance` | In-process (testing) | `Client(mcp)` |

---

## `mcp.run()` Transport Options

```python
mcp.run()                     # default: stdio
mcp.run(transport="stdio")    # explicit stdio
mcp.run(transport="sse")      # HTTP + SSE (Phase 5)
mcp.run(transport="sse", host="0.0.0.0", port=8000)
```

---

## Logging Setup (Mandatory Best Practice)

```python
import sys, logging

logging.basicConfig(
    stream=sys.stderr,          # NEVER sys.stdout in a stdio server
    level=logging.DEBUG,
    format="[%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

@mcp.tool()
def my_tool(x: str) -> str:
    logger.debug(f"my_tool called with x={x!r}")  # safe — goes to stderr
    return x.upper()
```

FastMCP sets this up automatically but being explicit is good practice. **Never** use bare `print()` in a stdio server without `file=sys.stderr`.

---

## Phase 2 vs Phase 3 Comparison

| What | Phase 2 (manual) | Phase 3 (FastMCP) |
|---|---|---|
| Handshake | ~30 lines | **0 lines** — automatic |
| Tool registration | Dict dispatch + manual schema | `@mcp.tool()` decorator |
| Schema generation | Written by hand | **From type hints** |
| stdout safety | You manage | **Framework manages** |
| Pydantic support | Manual | **Built-in** |
| Error handling | Manual `isError` | **`raise` anything** |
| Transport setup | Manual stdin loop | `mcp.run(transport="stdio")` |
| Total lines | ~150 | ~30 |

---

## Key Takeaways

1. `@mcp.tool()` + type hints + docstring = complete tool definition with auto-generated schema.
2. **Raise exceptions for errors** — FastMCP wraps them in `isError: true` content blocks.
3. **Pydantic models** give you nested input validation and rich schemas for free.
4. `mcp.run(transport="stdio")` replaces the entire manual stdin/stdout loop from Phase 2.
5. **FastMCP Client is async** because MCP I/O is async — always `async with Client(...) as c`.
6. `result.data` is your shortcut; `result.content[0].text` is the raw MCP content block.
7. Always configure logging to `stderr` — `stdout` is the protocol wire.
