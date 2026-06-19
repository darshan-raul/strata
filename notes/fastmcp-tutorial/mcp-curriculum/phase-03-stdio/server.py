# phase-03-stdio/server.py
#
# PURPOSE: The same server as Phase 2 — but written with FastMCP.
# Compare this to phase-02-jsonrpc/minimal_server.py line by line.
# Everything you wrote manually there is now handled by the framework.
#
# Run standalone:  python3 server.py
# Or via client:   python3 client.py

import sys
import logging
from fastmcp import FastMCP

# ─────────────────────────────────────────────────────────────────────────────
# RULE: In a stdio server, always configure logging to stderr explicitly.
# FastMCP does this automatically, but being explicit is good practice.
# This ensures NO log output ever touches stdout (which is the JSON-RPC wire).
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="[%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Create the FastMCP server instance
# The string argument is the server's name — shown in the initialize handshake
# ─────────────────────────────────────────────────────────────────────────────
mcp = FastMCP("phase-03-server")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1: greet
#
# FastMCP reads the type hints and docstring to produce this JSON Schema:
#   {
#     "type": "object",
#     "properties": {
#       "name": {"type": "string"}
#     },
#     "required": ["name"]
#   }
#
# The function's return value is automatically wrapped in:
#   {"content": [{"type": "text", "text": "<your return value>"}]}
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def greet(name: str) -> str:
    """Say hello to a person by name."""
    logger.debug(f"greet() called with name={name!r}")  # goes to stderr — safe
    return f"Hello, {name}! Welcome to MCP."


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2: add
#
# Notice: float type hint → JSON Schema "type": "number"
# Python type → JSON Schema type mapping:
#   str   → "string"
#   int   → "integer"
#   float → "number"
#   bool  → "boolean"
#   list  → "array"
#   dict  → "object"
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def add(a: float, b: float) -> str:
    """Add two numbers together."""
    logger.debug(f"add() called with a={a}, b={b}")
    result = a + b
    return f"{a} + {b} = {result}"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3: divide (demonstrates error handling)
#
# In MCP, there are TWO ways to signal an error:
#
# A) Raise a Python exception → FastMCP returns isError: true in result
#    (the content block contains the error message — LLM sees it and can react)
#
# B) Return normally → FastMCP returns isError: false
#
# Option A is preferred for "expected" domain errors (bad input, not found, etc.)
# The LLM can read the error and decide what to do (retry, rephrase, give up).
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def divide(numerator: float, denominator: float) -> str:
    """Divide numerator by denominator. Raises an error if denominator is zero."""
    if denominator == 0:
        raise ValueError("Cannot divide by zero.")
    result = numerator / denominator
    return f"{numerator} / {denominator} = {result:.4f}"


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4: describe_person (demonstrates Pydantic / complex types)
#
# You can use Pydantic models as parameters — FastMCP generates a nested schema.
# This is one of the most powerful FastMCP features for real-world tools.
# ─────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel, Field

class Person(BaseModel):
    name: str = Field(description="The person's full name")
    age: int = Field(description="The person's age in years", ge=0, le=150)
    role: str = Field(default="engineer", description="The person's job role")

@mcp.tool()
def describe_person(person: Person) -> str:
    """Generate a description of a person from their profile."""
    return (
        f"{person.name} is a {person.age}-year-old {person.role}."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
#
# mcp.run() does everything:
#   1. Detects the transport (stdio by default)
#   2. Sets up stdin/stdout handling
#   3. Runs the event loop
#   4. Handles the initialize handshake
#   5. Dispatches all incoming method calls
#
# Transport can be overridden: mcp.run(transport="sse") → Phase 5
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logger.info("Starting phase-03-server over stdio...")
    mcp.run(transport="stdio")
