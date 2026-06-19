# LangChain — Testing & Pitfalls

> **Part 8 of the LangChain deep-dive.** Testing the agent
> without hitting a real LLM (`FakeListChatModel`,
  `FakeMessagesListChatModel`), and the package-level gotchas
> that bite (import paths, version drift, deprecations).

The agent loop is testable in two layers:

1. **Unit tests** — the graph, the routing, the tool calls.
   Use `FakeListChatModel` to deterministically simulate the
   model. No network. No cost. Fast.
2. **Integration tests** — the model is real (or mocked at the
   HTTP layer with a LiteLLM stand-in). Slow, expensive, but
   catches prompt-quality issues.

Strata's Phase 2 pytest suite is unit tests with
`FakeMessagesListChatModel`. Integration tests land later
(Phase 3+).

---

## 1. `FakeListChatModel` — canned responses

The simplest fake model. You give it a list of `AIMessage`s;
it pops them in order on each `invoke` call.

```python
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

fake = FakeListChatModel(responses=[
    AIMessage(content="first response"),
    AIMessage(content="second response"),
    AIMessage(content="third response"),
])

# On each .invoke, the next response is returned:
fake.invoke("hi")      # AIMessage(content="first response")
fake.invoke("hi again") # AIMessage(content="second response")
# After the list is exhausted, IndexError.
```

Useful for testing "the model returns X and the graph does Y"
deterministically.

### Iterating forever

If you want a model that always returns the same response
(forever), pass an infinite iterator:

```python
import itertools
fake = FakeListChatModel(responses=itertools.repeat(
    AIMessage(content="ok")
))
```

### Including tool calls in the response

```python
fake = FakeListChatModel(responses=[
    AIMessage(
        content="",
        tool_calls=[ToolCall(name="list_clusters", args={}, id="call-1")],
    ),
    AIMessage(content="You have 3 clusters."),  # final response
])
```

The first call yields a tool-call-only `AIMessage`. The graph
runs `ToolNode`, gets the result, calls the model again, gets
the final response. Tests the full agent loop.

---

## 2. `FakeMessagesListChatModel` — canned responses with conversation tracking

`FakeMessagesListChatModel` is the upgrade: it returns the
*next* response based on the conversation state. Useful for
"given this conversation, return this."

```python
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

fake = FakeMessagesListChatModel(responses=[
    # Response 1: tool call
    AIMessage(content="", tool_calls=[
        ToolCall(name="list_clusters", args={}, id="call-1"),
    ]),
    # Response 2: final answer
    AIMessage(content="You have 3 clusters."),
])
```

Same as `FakeListChatModel` for sequential use. The difference
shows up in streaming-aware tests.

### Streaming with fakes

Both fakes support `stream` and return a single chunk:

```python
for chunk in fake.stream("hi"):
    print(chunk.content, end="")
# "first response"
```

The "streaming" is fake — you get the full response in one
chunk. But the graph's `ToolNode` and the `messages` reducer
work correctly.

---

## 3. `FakeListLLM` — for completion-style models

```python
from langchain_core.language_models.fake import FakeListLLM

fake = FakeListLLM(responses=["a", "b", "c"])
```

Used for legacy `LLM` (not `ChatModel`) code. Strata uses
chat models; you won't need this.

---

## 4. `FakeMessagesListChatModel` with `cycle=True`

```python
fake = FakeMessagesListChatModel(
    responses=[response1, response2, response3],
    cycle=True,    # when exhausted, loop back to the start
)
```

`cycle=True` is the answer to "my test makes 4 calls but I
only have 3 canned responses." It loops instead of erroring.

---

## 5. `patch_langchain_environment` — env isolation

```python
from langchain_core.env import patch_langchain_environment

with patch_langchain_environment():
    # Inside this block, env vars like LANGCHAIN_TRACING_V2 are stubbed
    # so tests don't accidentally hit LangSmith.
    ...
```

The default for `LANGCHAIN_TRACING_V2` in tests is unset, so
this is rarely needed. But if a test sets the env var, use
this to scope it.

---

## 6. Testing the graph

### Test 1: the right tool is called

```python
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import ToolNode
from app.graph import build_graph
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolCall

def test_list_clusters_called():
    fake = FakeMessagesListChatModel(responses=[
        AIMessage(
            content="",
            tool_calls=[ToolCall(name="list_clusters", args={}, id="call-1")],
        ),
        AIMessage(content="You have 3 clusters."),
    ])
    # Build a graph that uses the fake model
    # (assuming build_graph accepts an llm parameter or is patched)
    graph = build_graph(llm=fake)

    result = graph.invoke({"messages": [HumanMessage(content="list my clusters")]})

    # The tool call was made
    tool_calls = [m for m in result["messages"] if hasattr(m, "tool_calls")]
    assert any(
        call["name"] == "list_clusters"
        for m in tool_calls for call in m.tool_calls
    )
```

### Test 2: the tool result is in the next LLM call

```python
def test_tool_result_in_next_call():
    fake = FakeMessagesListChatModel(responses=[
        AIMessage(
            content="",
            tool_calls=[ToolCall(name="list_clusters", args={}, id="call-1")],
        ),
        AIMessage(content="You have 3 clusters."),
    ])
    graph = build_graph(llm=fake)
    result = graph.invoke({"messages": [HumanMessage(content="list")]})

    # The second model call (index 2 in messages, after the tool message)
    # should have received the tool result.
    messages = result["messages"]
    # The second AIMessage (the "You have 3 clusters" one) was the
    # second .invoke call. The input to that call is the messages
    # list as of just before it. The ToolMessage should be in there.
    last_ai_index = max(
        i for i, m in enumerate(messages) if isinstance(m, AIMessage)
    )
    messages_before_last_ai = messages[:last_ai_index]
    tool_messages = [m for m in messages_before_last_ai if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert "cl-001" in tool_messages[0].content
```

### Test 3: streaming emits `done` exactly once

```python
async def test_streaming_done():
    graph = build_graph(llm=fake)
    chunks = []
    async for chunk in graph.astream(
        {"messages": [HumanMessage(content="list")]},
        stream_mode="messages",
    ):
        chunks.append(chunk)
    # The final "done" event is custom; emit it in app/main.py
    # This test verifies the graph completes
    assert len(chunks) > 0
```

The "exactly one `done`" assertion is a property of `app/main.py`,
not the graph. Test that the streaming wrapper emits `done` once
and only once.

---

## 7. Testing tools in isolation

```python
from app.tools.list_clusters import list_clusters

def test_list_clusters_schema():
    schema = list_clusters.args_schema.model_json_schema()
    assert schema["type"] == "object"
    assert "properties" in schema
    # No required args
    assert schema.get("required", []) == []

def test_list_clusters_returns_expected():
    result = list_clusters.invoke({})
    assert isinstance(result, list)
    for cluster in result:
        assert "id" in cluster
        assert "status" in cluster
```

### Testing async tools

```python
import pytest

@pytest.mark.asyncio
async def test_list_clusters_async():
    result = await list_clusters.ainvoke({})
    assert isinstance(result, list)
```

---

## 8. The "no network" discipline

The test suite must not hit the network. Enforce:

```python
# conftest.py
import socket

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("Network call in test!")
    monkeypatch.setattr(socket, "socket", refuse)
```

Or use `pytest-socket`:

```toml
[tool.pytest.ini_options]
addopts = "--disable-socket"
```

This catches "I accidentally hit LiteLLM in a test" before it
costs you money.

---

## 9. Mocking the LiteLLM HTTP layer

For tests that exercise the agent but not the model, mock
LiteLLM at the HTTP layer:

```python
import pytest
from pytest_httpx import HTTPXMock

@pytest.fixture
def mock_litellm(httpx_mock):
    httpx_mock.add_response(
        url="http://litellm:4000/v1/chat/completions",
        json={
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        },
    )
    yield httpx_mock
```

But this is mostly unnecessary if you use `FakeListChatModel`
in the unit tests. Reserve for integration tests where you
want to verify "the real OpenAI request format is correct."

---

## 10. Testing cost / token usage

```python
def test_model_returns_usage_metadata():
    fake = FakeMessagesListChatModel(responses=[
        AIMessage(content="hi", usage_metadata={
            "input_tokens": 5, "output_tokens": 2, "total_tokens": 7,
        }),
    ])
    response = fake.invoke([])
    assert response.usage_metadata["total_tokens"] == 7
```

`FakeMessagesListChatModel` lets you set `usage_metadata` on
the response so you can test cost-tracking code without a real
model.

---

## 11. The package layout gotchas

LangChain has been reorganized several times. Things that
worked in 0.0.x may not work in 1.0.x.

### What's where in modern LangChain (0.3+ / 1.0+)

| What | Where to import from |
|---|---|
| `Runnable`, `RunnableLambda`, `RunnableSequence` | `langchain_core.runnables` |
| Messages (`HumanMessage`, etc.) | `langchain_core.messages` |
| `@tool` | `langchain_core.tools` |
| `BaseChatModel` | `langchain_core.language_models` |
| `FakeListChatModel`, `FakeMessagesListChatModel` | `langchain_core.language_models.fake_chat_models` |
| `BasePromptTemplate`, `ChatPromptTemplate` | `langchain_core.prompts` |
| `StrOutputParser`, `PydanticOutputParser` | `langchain_core.output_parsers` |
| `BaseCallbackHandler` | `langchain_core.callbacks` |
| `set_llm_cache` | `langchain_core.globals` |
| `InMemoryCache` | `langchain_core.caches` |
| `SQLiteCache` | `langchain_community.cache` (will move) |
| `RedisCache` | `langchain_community.cache` |
| `ChatOpenAI` | `langchain_openai` |
| `ChatBedrock` | `langchain_aws` |
| `ChatAnthropic` | `langchain_anthropic` |
| `ChatOllama` | `langchain_ollama` |

### What NOT to import

- `from langchain.tools import tool` — legacy. Use
  `from langchain_core.tools import tool`.
- `from langchain.chat_models import ChatOpenAI` — deprecated.
  Use `from langchain_openai import ChatOpenAI`.
- `from langchain.llms import OpenAI` — legacy completion model.
  Use `from langchain_openai import ChatOpenAI`.
- `from langchain.agents import AgentExecutor` — legacy. Use
  LangGraph.
- `from langchain.memory import ConversationBufferMemory` —
  legacy. Use a checkpointer.

### What changed between minor versions

- **0.0.x → 0.1:** `langchain_community` extraction.
- **0.1 → 0.2:** Move to provider packages. `langchain.llms`
  → `langchain_openai`, etc.
- **0.2 → 0.3:** Cleaner package boundaries. Some
  `langchain_community` modules promoted.
- **1.0:** (ongoing) further consolidation. Check release
  notes when bumping.

The Strata `pyproject.toml` pins `>=0.3` (or `>=1.0`). When
bumping past a major version, run the test suite and check
for `ImportError`.

### What to do when an `ImportError` shows up

1. **Find the new home.** The deprecation warning usually
   points at the new path.
2. **Update imports.** `grep -r "from langchain\." app/ tests/`
   to find all the old imports.
3. **Run the tests.** If something is now missing, look for
   the new API (it may have been renamed or moved to
   `langchain_community`).
4. **Pin the version in `pyproject.toml`.** If a regression
   bites, pin the previous version and file an issue.

---

## 12. Common pitfalls (recap from across the deep-dive)

1. **`base_url` must end in `/v1`.**
2. **`ToolMessage.content` is always a string.** Serialize Pydantic
   models with `model_dump_json()`.
3. **Mismatched `tool_call_id`** — `ToolNode` gets it right; you
   don't.
4. **`@tool` on a no-argument function** is fine. Schema is
   `{"properties": {}}`.
5. **`from_template` vs `from_messages`** — `from_template` is
   for single strings; `from_messages` for typed slot lists.
6. **Async tools** — `async def` the function and `@tool`
   without arguments.
7. **`bind_tools` returns a new `Runnable`**, not a modified
   model. The pattern is `llm.bind_tools(tools).invoke(messages)`.
8. **`with_structured_output` returns the parsed object**,
   not the `AIMessage`. Use `include_raw=True` for both.
9. **`set_llm_cache` is global** — affects all chat models in
   the process. Reset in tests.
10. **`astream_events(version="v2")`** — `version` is required
    and `"v2"` is the right value.
11. **`on_chat_model_end` hook is called once per model call,**
    not once per chunk. `on_chat_model_stream` is per chunk.
12. **LangChain memory classes are legacy.** Use a LangGraph
    checkpointer + a `MemoryStore` for long-term memory.
13. **`pydantic` v1 vs v2** — Pydantic v2 is required by
    modern LangChain. Don't `pip install pydantic==1.x`.
14. **`langchain_community` is being deprecated.** Prefer
    specific provider packages or `langchain_core` utilities.

---

## 13. Strata's testing plan

| Phase | Test type | What | How |
|---|---|---|---|
| 2 | Unit | Graph routing, tool schemas, prompt assembly. | `FakeMessagesListChatModel`. |
| 3 | Unit + integration | Real tool calls to the orchestrator. | `pytest-httpx` to mock the orchestrator. |
| 4 | Unit | RAG retrieve node. | Mock `retriever-service` with `httpx_mock`. |
| 5 | Integration | Real LiteLLM with Bedrock. | Only in CI if AWS creds are available. |
| 6 | E2E | Full chat → tool → orchestrator → AWS. | `kind` cluster + mocked AWS. |

The bar for Phase 2 is: `pytest` green, all 5 tools have
schema and return-shape tests, the graph has routing tests for
"list clusters", "get status", "provision".

---

## 14. What to read next

- The other parts of this deep-dive, especially
  `03-chat-models.md` (for the `bind_tools` tests) and
  `04-tools.md` (for the `@tool` schema tests).
- `../langgraph/12-pitfalls.md` — graph-level bugs.
- `../langgraph/11-deployment-and-debug.md` — debugging
  LangGraph apps in dev.
- LangChain testing guide: <https://python.langchain.com/docs/how_to/fake_chat_model/>
