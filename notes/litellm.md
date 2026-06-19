# LiteLLM

The OpenAI-compatible proxy that sits between Strata's agent-service
(and retriever-service, in Phase 4+) and the actual LLM/embedding
providers. One proxy, many providers, one set of observability knobs,
zero vendor SDK code in our Python service.

Strata uses LiteLLM in a strict way:

1. **Single proxy deployment in the `strata` namespace** (Phase 2+).
2. **`ChatOpenAI` (LangChain) calls it via `base_url`**, not direct
   vendor SDKs.
3. **All model routing goes through the `model_list` config**, so
   swapping Bedrock for OpenAI is a ConfigMap change.

---

## 1. Mental model

LiteLLM is a Python (or Docker) HTTP service that:

- Accepts requests on `/v1/chat/completions`, `/v1/embeddings`,
  `/v1/completions` — exactly the OpenAI API shape.
- Looks up the model in a `model_list` and routes the call to the
  correct provider (Bedrock, OpenAI, Anthropic, Ollama, ...).
- Translates the request/response between OpenAI format and the
  provider's native format.
- Adds cross-cutting features: retries, fallbacks, rate limits,
  cost tracking, virtual keys.

**Why a proxy and not direct SDK calls?** Three reasons that matter
for Strata:

1. **Centralized model swap.** The agent-service deployment env
   points at `http://litellm:4000`. To switch from Bedrock Nova Pro
   to OpenAI gpt-4o, you change the `model_list` ConfigMap. No
   agent-service rebuild.
2. **Centralized credential management.** The AWS access key sits
   in a k8s Secret, mounted only on the LiteLLM Deployment. The
   agent-service doesn't see AWS creds.
3. **Provider fallback.** If Bedrock is degraded, LiteLLM can
   fall back to Anthropic (or whatever). Same config, no agent
   changes.

The cost is one extra network hop per LLM call. Inside a cluster,
that's microseconds. Outside (e.g. calling LiteLLM from your laptop
during dev), it's a real roundtrip — but the dev target is the
Kind cluster, not the laptop, so this doesn't bite us.

---

## 2. The `model_list` config

This is the only config file that matters. Strata's is at
`control-plane/manifests/10-litellm/configmap.yaml`:

```yaml
model_list:
  - model_name: nova-pro
    litellm_params:
      model: bedrock/amazon.nova-pro-v1:0
      aws_region_name: us-east-1
  - model_name: titan-embed-v2
    litellm_params:
      model: bedrock/amazon.titan-embed-text-v2:0
      aws_region_name: us-east-1
```

`model_name` is **the alias the caller uses**. The agent-service's
`ChatOpenAI(model="nova-pro", ...)` says "nova-pro"; LiteLLM looks
up `nova-pro` in `model_list` and routes to `bedrock/amazon.nova-pro-v1:0`.

`litellm_params.model` is the **provider-prefixed model id**. The
prefix `bedrock/`, `openai/`, `anthropic/`, `ollama/` selects the
provider. The rest of the string is provider-specific.

### Provider prefixes

| Prefix | Provider | Model id example |
|---|---|---|
| `bedrock/` | AWS Bedrock | `bedrock/amazon.nova-pro-v1:0` |
| `openai/` | OpenAI | `openai/gpt-4o` |
| `anthropic/` | Anthropic (direct) | `anthropic/claude-3-5-sonnet-20241022` |
| `ollama/` | Ollama (local) | `ollama/llama3.1:8b` |
| `azure/` | Azure OpenAI | `azure/my-deployment` |
| `vertex_ai/` | GCP Vertex | `vertex_ai/gemini-1.5-pro` |

For our purposes, the `bedrock/` prefix is what we use. Phase 6+
might add a `bedrock_converse/` prefix for newer Bedrock features.

### Bedrock-specific params

```yaml
litellm_params:
  model: bedrock/amazon.nova-pro-v1:0
  aws_region_name: us-east-1
  aws_access_key_id: os.environ/AWS_ACCESS_KEY_ID
  aws_secret_access_key: os.environ/AWS_SECRET_ACCESS_KEY
```

The `os.environ/...` syntax tells LiteLLM to read the value from
the env var at request time, not bake it into the config. Strata
mounts these as env vars from a k8s Secret.

### Cross-region inference

For Bedrock, `aws_region_name` is the inference region. Some models
are only available in certain regions. Nova Pro is in us-east-1,
us-west-2, eu-west-1, etc. Set the region to one your AWS account
has model access for.

---

## 3. Embeddings

Same config pattern, different model:

```yaml
- model_name: titan-embed-v2
  litellm_params:
    model: bedrock/amazon.titan-embed-text-v2:0
    aws_region_name: us-east-1
```

Caller (the `retriever-service` Go code, in Phase 4) does:

```bash
curl -X POST http://litellm:4000/v1/embeddings \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "titan-embed-v2", "input": "some text"}'
```

Response:

```json
{
  "object": "list",
  "data": [{"object": "embedding", "embedding": [0.012, -0.034, ...], "index": 0}],
  "model": "titan-embed-text-v2:0",
  "usage": {"prompt_tokens": 3, "total_tokens": 3}
}
```

The embedding is a 1024-dim float vector. Qdrant stores it as a
1024-dim point. See `docs/rag.md` for the full pipeline.

### Embedding dim gotcha

Different embedding models produce different-dim vectors:

| Model | Dim |
|---|---|
| `amazon.titan-embed-text-v1` | 1536 |
| `amazon.titan-embed-text-v2:0` | 1024 (default) — also supports 256, 512 |
| `amazon.titan-embed-image-v1` | 1024 |
| `cohere.embed-english-v3` | 1024 |
| `openai.text-embedding-3-small` | 1536 (default) — also supports 512, 1536 |
| `openai.text-embedding-3-large` | 3072 |

Qdrant collections are typed to a single dim. If you switch models,
**recreate the collection** (or run a migration). For Titan v2 we
stay on 1024.

---

## 4. Auth and the master key

LiteLLM has two auth concepts:

1. **Master key** — admin key. Can read/write the `model_list` and
   the key store. Strata sets this from a k8s Secret.
2. **Virtual keys** — per-caller keys, optionally with rate limits
   and model restrictions. Created via the `/key/generate` endpoint.
   For Phase 2 we use the master key for everything; Phase 6+
   introduces virtual keys per user (post-auth).

In `app/providers/litellm_provider.py`:

```python
ChatOpenAI(
    model=model_name,
    base_url=f"{LITELLM_BASE_URL}/v1",
    api_key=os.environ["LITELLM_API_KEY"],   # master key in Phase 2
    ...
)
```

`ChatOpenAI` sends the key in `Authorization: Bearer <key>`. LiteLLM
accepts it. Done.

---

## 5. Retries, fallbacks, and resilience

```yaml
router_settings:
  num_retries: 2
  timeout: 60
  fallbacks:
    - nova-pro
    - anthropic/claude-3-5-haiku-20241022
```

- `num_retries` — retry transient errors (throttling, 5xx). Do not
  retry 4xx (your request is broken).
- `timeout` — seconds before LiteLLM cancels the upstream call.
- `fallbacks` — list of model_name aliases to try in order if the
  primary model errors out. Useful for Bedrock throttling —
  Anthropic is a different provider with a different rate-limit pool.

For Phase 2, simple retries are enough. Fallbacks are a Phase 4+
addition once we care about reliability.

---

## 6. Observability — what to monitor

LiteLLM exposes a virtual-key log and (with a `litellm` callback
config) can emit to Langfuse, Datadog, OpenTelemetry, etc. Strata
defers this to Phase 6 (PLG stack). For Phase 2, the only
observability is:

- `kubectl logs -n strata -l app=litellm` — proxy logs, including
  request/response timing.
- `curl http://litellm:4000/health/liveliness` — readiness probe.
- The response's `usage` field — token counts.

In `app/main.py`, Strata does NOT yet log token usage per request.
That's a Phase 5 add (the `POST /chat` response should include
`tokens_in`, `tokens_out` for cost tracking).

---

## 7. Local dev — running LiteLLM in the Kind cluster

The deployment is a vanilla `ghcr.io/berriai/litellm:main-stable`
image with:

- `configmap.yaml` mounted at `/etc/litellm/config.yaml`
- `secret.yaml` env vars for AWS creds + master key
- args: `--config /etc/litellm/config.yaml --port 4000`

The image is ~1.5GB. It cold-starts in ~20s. The readiness probe
hits `/health/liveliness` which is cheap.

### Tearing it down

```bash
make delete-litellm
# or
kubectl delete -f control-plane/manifests/10-litellm/
```

The k8s Secret is the only piece with real AWS creds. Don't commit
it. `secret.yaml.example` is the template; copy to `secret.yaml`
and fill in values; `secret.yaml` is gitignored.

### Swapping model providers

To switch to OpenAI:

1. Edit `configmap.yaml`:

   ```yaml
   model_list:
     - model_name: nova-pro
       litellm_params:
         model: openai/gpt-4o-mini
   ```

2. Edit `secret.yaml`:

   ```yaml
   OPENAI_API_KEY: sk-...
   LITELLM_MASTER_KEY: sk-dev-strata-litellm-change-me
   ```

3. Add env var to LiteLLM Deployment:

   ```yaml
   env:
     - name: OPENAI_API_KEY
       valueFrom:
         secretKeyRef:
           name: litellm-aws-credentials
           key: OPENAI_API_KEY
   ```

4. `make apply-litellm`. Done. The agent-service doesn't change.

To use Anthropic, `openai/` → `anthropic/`, `OPENAI_API_KEY` →
`ANTHROPIC_API_KEY`, model id `claude-3-5-sonnet-20241022`. Same
pattern.

### Ollama for offline dev

`ollama/llama3.1:8b` works with a local Ollama server (or an
Ollama Deployment in Kind). Slower inference, weaker model, no
API key, no AWS creds. Good for "I have a flight, can I still
develop the agent?" Yes.

---

## 8. Common pitfalls

1. **`base_url` for `ChatOpenAI` must end in `/v1`**, not
   `/chat/completions`. LiteLLM's full OpenAI-compat surface is
   at `http://litellm:4000/v1`. See
   `app/providers/litellm_provider.py`.
2. **`api_key` is required even if you don't set a master key on
   LiteLLM.** `ChatOpenAI` will error without one. Use
   `api_key="sk-no-auth"` if you disable auth.
3. **The model name passed to `ChatOpenAI(model=...)` is the
   alias from `model_list`, not the provider-prefixed id.** Pass
   `"nova-pro"`, not `"bedrock/amazon.nova-pro-v1:0"`. If you
   pass the prefixed id, LiteLLM accepts it (it tries to look up
   "bedrock/...") but you've bypassed the aliasing benefit.
4. **Bedrock models require `aws_region_name`** in `litellm_params`.
   LiteLLM does not infer it from the env var alone.
5. **Bedrock throttling is a real thing.** Nova Pro has a per-region
   TPM (tokens per minute) quota. In high-traffic, retries +
   fallbacks help. In dev, irrelevant.
6. **The LiteLLM Docker image is heavy.** ~1.5GB. Cold-start
   ~20s. If you're rebuilding the Kind cluster a lot, consider
   pre-pulling the image.

---

## 9. What to read next

- `docs/bedrock.md` — what Bedrock is and how the model IDs work.
- `docs/langchain.md` — `ChatOpenAI` and how Strata uses it.
- `docs/rag.md` — the embedding pipeline.
- LiteLLM docs: <https://docs.litellm.ai/docs/>
- LiteLLM Bedrock provider: <https://docs.litellm.ai/docs/providers/bedrock>
