# LangChain — Prompts & Output Parsers

> **Part 5 of the LangChain deep-dive.** `ChatPromptTemplate`,
> `MessagesPlaceholder`, the `partial` and templating rules, and
> the output-parser family (`PydanticOutputParser`,
> `JsonOutputParser`, retry parsers).

Prompts are where the model behavior is actually configured. The
system message is the main lever. For static systems, you can use
a literal `SystemMessage`. For systems with variables (per-user
context, per-environment instructions, retrieved docs), use
`ChatPromptTemplate`.

Output parsers are the inverse: a way to force the model's
response to conform to a schema. Less useful for chat agents
(tools handle structured output there), but essential for
non-tool flows (extraction, classification, structured QA).

---

## 1. `ChatPromptTemplate` — the system-prompt factory

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are Strata, an EKS ops copilot. Domain: {domain}."),
    ("placeholder", "{messages}"),
])

# To invoke:
formatted = prompt.invoke({
    "domain": "production",
    "messages": [HumanMessage(content="list my clusters")],
})
# formatted is a PromptValue (a list of messages ready to send)
```

The four slot types you'll use:

| Slot | What it represents | Usage |
|---|---|---|
| `("system", "...")` | A system message. | Static instructions, persona, rules. |
| `("human", "...")` | A human message. | Static or templated user input. |
| `("ai", "...")` | An AI message. | Few-shot example. |
| `("placeholder", "{name}")` | A slot for messages. | Inject the conversation history at this position. |

`("placeholder", "{messages}")` is the canonical pattern for
chat: the prompt has the system + the entire conversation
history.

### Variable syntax

Inside message strings, `{var}` is a template variable. The
prompt is a `PromptTemplate` under the hood.

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a copilot for {domain}."),
    ("human", "Question: {question}"),
])

prompt.invoke({"domain": "EKS", "question": "How do I create a cluster?"})
```

The `{}` syntax is a Python format string. If you need literal
braces in the output, escape them: `{{` and `}}`.

### A more complex example

```python
few_shot_prompt = ChatPromptTemplate.from_messages([
    ("system", "You translate AWS errors into actionable steps."),
    ("human", "AccessDenied: User is not authorized to perform eks:CreateCluster"),
    ("ai", "1. Verify the IAM role has eks:CreateCluster permission. "
           "2. Check the trust relationship. "
           "3. Try assuming the role and call sts:GetCallerIdentity."),
    ("human", "{error}"),
])
```

The `("human", ...)` / `("ai", ...)` pair above the templated
`("human", "{error}")` is a few-shot example. The model learns
the format.

### `from_template` vs `from_messages`

```python
# from_messages: a list of typed slots
ChatPromptTemplate.from_messages([("system", "..."), ("human", "...")])

# from_template: a single string (defaults to "human" role)
ChatPromptTemplate.from_template("Translate to French: {text}")
```

`from_template` is a shortcut for "a single human message
template." Use it for one-shot prompts (extraction,
classification).

---

## 2. `MessagesPlaceholder` — the explicit form

`("placeholder", "{messages}")` is a shorthand. The explicit form
is `MessagesPlaceholder`:

```python
from langchain_core.prompts import MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are Strata."),
    MessagesPlaceholder("history", optional=True),   # all prior turns
    ("human", "{question}"),
])
```

Why the explicit form is sometimes better:

- **`optional=True`** — the prompt works even if `history` is
  missing. The shorthand form errors on missing.
- **Variable name overriding** — useful if your state has
  multiple message lists (e.g. `messages` and `short_term_memory`).
- **Partial application** — easier to add messages after the
  prompt is built.

---

## 3. `partial` — pre-fill some variables

`prompt.partial(**kwargs)` returns a new prompt with some
variables already filled in. Useful when the variables come
from runtime config rather than user input.

```python
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a copilot for {user_name} in {region}."),
    ("placeholder", "{messages}"),
])

# At module load:
prompt = prompt.partial(user_name="darshan", region="us-west-2")

# At call time:
prompt.invoke({"messages": [...]})   # user_name and region already set
```

### `partial` from a `Runnable`

```python
from datetime import datetime

def current_date(_):
    return datetime.now().strftime("%Y-%m-%d")

prompt = prompt.partial(date=RunnableLambda(current_date))
```

The `partial` value can be a function (wrapped in
`RunnableLambda`) for dynamic partials. The function gets the
input and returns a string.

---

## 4. Pipeline: `prompt | model | parser`

The canonical "chain" in LangChain.

```python
from langchain_core.output_parsers import StrOutputParser

chain = prompt | model | StrOutputParser()

result = chain.invoke({"messages": [HumanMessage(content="hi")]})
# result is a plain string, not an AIMessage
```

`StrOutputParser` extracts `AIMessage.content` and returns it as
a string. Useful when you want the final answer as a string and
don't care about the rest of the message.

**Strata does not use chains in production.** The graph does the
work. But you'll see `prompt | model | parser` everywhere in
LangChain tutorials. Understand it.

---

## 5. `PromptTemplate` (non-chat)

```python
from langchain_core.prompts import PromptTemplate

PromptTemplate.from_template("Translate to French: {text}")
# Result is a string, not a list of messages.
```

Use for completion-style models (legacy) or when feeding a
string into a non-chat LLM. Strata uses chat models only.

---

## 6. `FewShotPromptTemplate` / `FewShotChatMessagePromptTemplate`

Few-shot examples. The `FewShotChatMessagePromptTemplate` is the
chat-aware form.

```python
from langchain_core.prompts import FewShotChatMessagePromptTemplate

examples = [
    {"input": "AccessDenied on eks:CreateCluster", "output": "Check IAM role."},
    {"input": "ResourceNotFound on ec2:DescribeVPC", "output": "Verify the VPC id."},
]

example_prompt = ChatPromptTemplate.from_messages([
    ("human", "{input}"),
    ("ai", "{output}"),
])

few_shot = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    examples=examples,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "Translate AWS errors to actions."),
    few_shot,
    ("human", "{query}"),
])
```

The few-shot examples get injected between the system and the
user's query. The model sees them and follows the format.

### Dynamic example selection

`ExampleSelector` picks which examples to show based on the
input. The `SemanticSimilarityExampleSelector` uses embeddings
to find the most relevant few-shot examples.

```python
from langchain_core.example_selectors import SemanticSimilarityExampleSelector
from langchain_openai import OpenAIEmbeddings

selector = SemanticSimilarityExampleSelector.from_examples(
    examples,
    OpenAIEmbeddings(model="text-embedding-3-small"),
    Chroma,
    k=2,    # top 2 most similar examples
)

dynamic_prompt = FewShotChatMessagePromptTemplate(
    example_prompt=example_prompt,
    example_selector=selector,
)
```

Strata's Phase 4+ RAG: when the retriever finds relevant docs,
inject them as the "few-shot context" instead of pre-written
examples.

---

## 7. Output parsers

Output parsers turn an `AIMessage` into something structured.
The family:

| Parser | Input | Output |
|---|---|---|
| `StrOutputParser` | `AIMessage` | `str` (the `content` field) |
| `BytesOutputParser` | `AIMessage` | `bytes` (UTF-8 encoded) |
| `JsonOutputParser` | `AIMessage` | `dict` (parsed JSON) |
| `PydanticOutputParser` | `AIMessage` | Pydantic model instance |
| `XMLOutputParser` | `AIMessage` | XML string or dict |
| `OutputFixingParser` | parser + LLM | Retries via LLM on parse failure |
| `RetryWithErrorOutputParser` | parser + LLM | Retries via LLM with the error in the prompt |

### `PydanticOutputParser`

The workhorse:

```python
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

class Answer(BaseModel):
    summary: str = Field(description="A 1-2 sentence summary.")
    citations: list[str] = Field(description="Doc ids that informed the answer.")
    confidence: float = Field(description="0 to 1.")

parser = PydanticOutputParser(pydantic_object=Answer)

# The parser's format instructions go into the prompt:
prompt = ChatPromptTemplate.from_messages([
    ("system", "Answer the question.\n\n{format_instructions}"),
    ("human", "{question}"),
]).partial(format_instructions=parser.get_format_instructions())

chain = prompt | model | parser

result = chain.invoke({"question": "What's Bedrock Nova Pro?"})
# result is an Answer instance
```

`parser.get_format_instructions()` returns a string the model
sees telling it "respond with JSON matching this schema." The
parser then `json.loads` the model's response and validates
against the Pydantic model.

### `JsonOutputParser`

Like `PydanticOutputParser` but for a `TypedDict` or arbitrary
JSON schema. Use when you don't want the Pydantic validation
overhead or when the schema is from a 3rd party (OpenAPI,
JSON Schema, etc.).

```python
from langchain_core.output_parsers import JsonOutputParser

parser = JsonOutputParser(pydantic_object=Answer)
# or:
parser = JsonOutputParser()    # free-form dict
```

### `OutputFixingParser` — retry on parse failure

```python
from langchain_core.output_parsers import OutputFixingParser

parser = OutputFixingParser.from_llm(
    parser=PydanticOutputParser(pydantic_object=Answer),
    llm=ChatOpenAI(model="gpt-4o-mini"),
)
```

If the model's first response doesn't parse, `OutputFixingParser`
sends the broken output + the error message back to a (cheaper)
LLM with "fix this" instructions. The fixed output is parsed
again.

### `RetryWithErrorOutputParser` — embed the error in the prompt

```python
from langchain_core.output_parsers import RetryWithErrorOutputParser

parser = RetryWithErrorOutputParser.from_llm(
    parser=PydanticOutputParser(pydantic_object=Answer),
    llm=ChatOpenAI(model="gpt-4o-mini"),
)
```

Similar to `OutputFixingParser` but the retry is done by
re-running the whole chain with the error in the prompt. Slower
but more reliable.

### `parse(partial=True)` — streaming

```python
parser = PydanticOutputParser(pydantic_object=Answer)
async for partial in parser.transform(aiter_chunks):
    print(partial)
```

With `partial=True`, the parser emits partial results as the
JSON streams in. Useful for "show me the answer as it
generates." This is finicky and the partial objects are
incomplete — usually you don't need it.

---

## 8. Strata's actual prompt usage

### Phase 2 — literal `SystemMessage`

```python
SYSTEM_PROMPT = """You are Strata, an EKS ops copilot.

You help the user manage their EKS clusters. Always:
- Call list_clusters before answering questions about clusters.
- Be precise about cluster ids and statuses.
- If a tool returns an error, explain it to the user and suggest next steps.
"""

# In call_model node:
def call_model(state: AgentState) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.bind_tools(tools).invoke(messages)
    return {"messages": [response]}
```

No `ChatPromptTemplate` yet. The system prompt is a constant.

### Phase 4+ — add retrieved docs

```python
def call_model(state: AgentState) -> dict:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        # The retrieve node may have injected a system message with context.
        *state["messages"],
    ]
    response = llm.bind_tools(tools).invoke(messages)
    return {"messages": [response]}
```

The retrieve node (Phase 4+) injects a `SystemMessage` with the
retrieved context. The prompt stays a literal; the variable
content comes from the state.

### Phase 6+ — multi-user, role-based, with RAG

```python
prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are Strata, an EKS ops copilot for {user_name} ({role}). "
     "Domain: {domain}. Permissions: {permissions}."),
    ("system", "{retrieved_context}"),    # injected by retrieve node
    MessagesPlaceholder("messages", optional=True),
]).partial(
    user_name=runtime_configurable("user_name"),
    role=runtime_configurable("role"),
    domain=runtime_configurable("domain"),
    permissions=runtime_configurable("permissions"),
    retrieved_context=retrieved_docs_node,    # depends on the state
)
```

This is overkill for Phase 2 but illustrates when
`ChatPromptTemplate` becomes necessary — when the system message
has variables from multiple sources.

---

## 9. `format_instructions` — the prompt-injection surface

`PydanticOutputParser.get_format_instructions()` returns a
string that tells the model to respond in a specific JSON
shape. The model is being **prompted** to follow the format;
nothing structural forces it. If the model misbehaves, the
parser fails.

The format instructions look like:

```
The output should be formatted as a JSON instance that conforms to the JSON schema below.

As an example, for the schema {"properties": {"foo": {"title": "Foo", "type": "string"}}, "required": ["foo"]}, the object {"foo": "bar"} is a well-formatted instance.

The schema:
{"properties": {"summary": {...}, "citations": {...}, "confidence": {...}}, "required": ["summary", "citations", "confidence"]}
```

You can customize this for clarity:

```python
parser = PydanticOutputParser(
    pydantic_object=Answer,
    # Custom instructions for the model
)
```

Strata's pattern: for simple cases (the RAG "did the docs
answer?" check), use `with_structured_output` instead — it
bypasses the prompt-based approach and uses tool calling
under the hood, which is more reliable.

---

## 10. Common pitfalls

1. **Forgetting `MessagesPlaceholder` for chat history.** If
   your prompt is just `("system", ...) + ("human", "...")`
   with no placeholder, the conversation history isn't passed
   in. The model sees only the latest human message and the
   system prompt. Use `("placeholder", "{messages}")` or
   `MessagesPlaceholder("messages")`.
2. **`{` in the prompt string.** Python format strings. Escape
   with `{{` and `}}`.
3. **`PydanticOutputParser` fails silently on missing fields.**
   The `ValidationError` raises on `invoke`, not on
   construction. Catch it in your tool/chain.
4. **`OutputFixingParser` retries with the same LLM.** If the
   original model can't follow the schema, a "fix" call to
   itself won't help. Use a different (usually cheaper)
   model for the repair.
5. **Putting retrieval results in the `human` slot.** The model
   treats the human slot as user input, not instructions. RAG
   context belongs in a `system` message.
6. **Mixing `from_template` and `from_messages`.** `from_template`
   is for single-string prompts. If you need slots, use
   `from_messages`.
7. **Forgetting `partial` is not free.** Each call to
   `partial(...)` returns a new prompt. If you do it in a hot
   loop, you're constructing prompts. Build the partially-applied
   prompt once at module scope.

---

## 11. What to read next

- `06-runnables-and-streaming.md` — how `prompt | model | parser`
  composes in the `Runnable` system.
- `../langgraph/02-state-and-reducers.md` — how messages get into
  the state and how to inject system messages from a node.
- LangChain prompts: <https://python.langchain.com/docs/concepts/prompt_templates/>
- LangChain output parsers: <https://python.langchain.com/docs/concepts/output_parsers/>
