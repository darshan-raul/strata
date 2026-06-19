# FastMCP Curriculum

A practical, thorough curriculum for learning FastMCP from zero to building
a production-grade AWS MCP server with a LangGraph + Textual TUI.

---

## Prerequisites

- Python: intermediate (async/await, decorators, type hints)
- AWS: boto3 set up, familiar with S3/EC2/IAM
- TUI: some experience with CLI tools

---

## Setup

```bash
# All phases share one uv project at the root
cd mcp-curriculum
uv run python <phase-XX>/client.py
```

---

## Phase Map

| Phase | Topic | Key Skills |
|---|---|---|
| [Phase 2](./phase-02-jsonrpc/) | JSON-RPC Under the Hood | Protocol semantics, handshake, stdio vs SSE |
| [Phase 3](./phase-03-stdio/) | First FastMCP Server (stdio) | `@mcp.tool()`, type hints → schema, FastMCP Client |
| [Phase 4](./phase-04-primitives/) | All Four Primitives | Tools, Resources, Prompts, Context |
| [Phase 5](./phase-05-sse/) | SSE Transport | HTTP server, `uvicorn`, multi-client, curl testing |
| [Phase 6](./phase-06-advanced/) | Advanced Patterns | Lifespan, routers, middleware, observability |
| [Phase 7](./phase-07-aws-server/) | AWS MCP Server | S3/EC2/IAM tools, aioboto3, dual transport |
| [Phase 8](./phase-08-langgraph/) | LangGraph Agent | ReAct agent, MCP client integration, tool-call loop |
| [Phase 9](./phase-09-tui/) | Textual TUI | Chat UI, LangGraph wiring, live tool output |
| [Phase 10](./phase-10-deploy/) | Polish & Deploy | IAM security, secrets, Docker, packaging, tests |

---

## Each Phase Contains

```
phase-XX-name/
├── GUIDE.md      ← Comprehensive reference (read this to review or revisit)
├── server.py     ← The FastMCP server for this phase
├── client.py     ← The client that exercises the server
└── ...           ← Additional files specific to the phase
```

---

## FastMCP 3.x Quick Reference

### Tool result
```python
result = await client.call_tool("name", {"arg": "val"})
result.data                 # plain Python value
result.content[0].text      # MCP text content block
result.is_error             # True if tool raised an exception
result.structured_content   # parsed JSON for dict/list returns
```

### Resource read (from client)
```python
contents = await client.read_resource("config://app/settings")
contents[0].text            # TextResourceContents.text
```

### Resource read (from inside a tool via ctx)
```python
result = await ctx.read_resource("config://app/settings")
result.contents[0].content  # ResourceResult.contents[0].content
```

### Context methods
```python
await ctx.info("message")
await ctx.debug("message")
await ctx.warning("message")
await ctx.error("message")
await ctx.report_progress(current, total)
result = await ctx.read_resource("uri://...")
```
