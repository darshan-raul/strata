# strata-agent-service

The Strata co-pilot. A LangGraph agent over a LiteLLM proxy, with mocked
EKS tools. Phase 2: no real backend, no real clusters, no real AWS
wiring — just the agent loop, end to end, talking to a fake LiteLLM
that proxies to Bedrock.

## Layout

```
app/
  main.py          # FastAPI, POST /chat streams NDJSON
  graph.py         # LangGraph state machine: call_model → tools or END
  state.py         # typed state (messages, thread_id)
  providers/
    litellm_provider.py   # thin wrapper over the OpenAI-compatible API
  tools/           # five mocked tools, all return Pydantic-shaped dicts
tests/             # pytest; uses FakeListChatModel, no real LLM needed
Dockerfile         # python:3.12-slim + uv
```

## Run locally (no k8s)

```bash
cd services/agent-service
uv sync
LITELLM_BASE_URL=http://localhost:4000 \
  LITELLM_API_KEY=sk-dev \
  MODEL_NAME=nova-pro \
  uv run uvicorn app.main:app --reload --port 8080
```

You'll need a LiteLLM proxy on `localhost:4000`. Easiest way:

```bash
pip install 'litellm[proxy]'
LITELLM_MASTER_KEY=sk-dev \
  AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-east-1 \
  litellm --model bedrock/amazon.nova-pro-v1:0 --port 4000
```

## Run in Kind (the dev target)

```bash
cd ../../                # back to repo root
make kind-up             # create kind cluster + local registry
make build               # build agent-service image
make apply               # kubectl apply -f control-plane/manifests/
make chat                # port-forward + curl /chat
make logs-agent          # tail agent-service logs
```

The agent is reachable on `localhost:8080` (mapped from NodePort 30800).

## Test

```bash
uv run pytest            # unit tests, no LLM needed
```

## Adding a new tool

1. Create `app/tools/<name>.py`. Decorate a function with `@tool("name")`.
   The function's docstring is the tool description (the LLM sees it).
2. Add the function to `_build_tools()` in `app/graph.py`.
3. Add a test in `tests/test_tools.py`.

Tool shape contract: the function returns either a Pydantic model
(`.model_dump()` to a dict) or a plain dict. The LLM receives the dict
as the tool result.
