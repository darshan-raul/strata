# AWS Bedrock

The AWS-managed service that hosts foundation models from multiple
providers (Anthropic, Meta, Mistral, Amazon, Cohere, Stability)
behind a single API. Strata uses Bedrock for both chat (Nova Pro)
and embeddings (Titan v2) because:

1. **It's the AWS-native answer.** If you're already on AWS, the
   billing, IAM, and VPC integration are consistent.
2. **It keeps the LiteLLM proxy simple.** Bedrock uses SigV4 auth
   with the AWS access key you already have.
3. **Titan v2 embeddings are cheap, fast, and good enough for our
   v1.** Multi-lingual, 1024-dim, $0.02 per 1M tokens.

You never call Bedrock directly in Strata code. LiteLLM does. This
doc covers what you need to know to debug "why is my LLM call
failing" and "how do I add a new model."

---

## 1. Mental model

Bedrock is a regional AWS service. You enable models per region,
per account. To use a model:

1. **Subscribe to the model** in the Bedrock console (or via
   API). One-time per account per region.
2. **Have IAM permissions** for `bedrock:InvokeModel` (and
   `bedrock:InvokeModelWithResponseStream` for streaming) on the
   specific model ARN.
3. **Call the model** via SDK or API. Bedrock exposes a
   `Converse`/`ConverseStream` API (newer, model-agnostic) and the
   older `InvokeModel`/`InvokeModelWithResponseStream` API
   (provider-specific request schemas).

LiteLLM uses the new `Converse` API where supported, falls back to
`InvokeModel` for older models. As a Strata user, you don't pick —
LiteLLM picks.

### Regions

Bedrock models are available in specific regions. Common ones:

- `us-east-1` — most models available
- `us-west-2` — most models available
- `eu-west-1` — fewer models, GDPR
- `ap-northeast-1` — fewer models
- `ap-south-1` (Mumbai) — limited

For Strata's dev target, **`us-east-1` is the safe default**. All
the models we use are available there. If you want to use a region
without a model, LiteLLM returns an error at request time.

### Cross-region inference (CRIS)

Some Bedrock models support "cross-region inference profiles" —
the same model id routed through any of several regions. This
spreads load and helps with regional throttling. CRIS model ids
look like `us.amazon.nova-pro-v1:0` instead of
`amazon.nova-pro-v1:0`. Strata doesn't use CRIS in Phase 2;
relevant for Phase 6+ if we hit regional throttling.

---

## 2. Models Strata uses

### Chat: `amazon.nova-pro-v1:0`

Amazon's flagship "balanced" model. Multimodal (text + image +
video in, text out). Reasonable price/performance.

| Property | Value |
|---|---|
| Model id (LiteLLM) | `bedrock/amazon.nova-pro-v1:0` |
| Model id (raw) | `amazon.nova-pro-v1:0` |
| Context window | 300K tokens |
| Max output | 5K tokens |
| Pricing (input) | $0.0008 per 1K tokens |
| Pricing (output) | $0.0032 per 1K tokens |
| Streaming | Yes (`InvokeModelWithResponseStream`) |
| Tool calling | Yes |
| Vision | Yes (not used in Strata) |

For comparison, the other chat models in the Nova family:

- `amazon.nova-micro-v1:0` — fastest, cheapest ($0.000035/$0.00014
  per 1K). Good for high-volume, low-stakes tasks. Strata could use
  this for `intent classification` and `entity extraction` in
  later phases.
- `amazon.nova-lite-v1:0` — fast multimodal. Middle ground.
- `amazon.nova-premier-v1:0` — top of the line. $$$.

For Phase 2 we use Nova Pro. The LiteLLM config swaps it for
whatever we want:

```yaml
- model_name: nova-pro
  litellm_params:
    model: bedrock/amazon.nova-pro-v1:0
    aws_region_name: us-east-1
```

If you don't have Nova Pro access in your account, swap to
`anthropic.claude-3-5-haiku-20241022` (Anthropic on Bedrock) — same
config shape, same pricing ballpark, and Bedrock has it in most
regions.

### Embeddings: `amazon.titan-embed-text-v2:0`

Amazon's text embedding model. Cheaper than OpenAI text-embedding-3,
good for English, supports variable dim.

| Property | Value |
|---|---|
| Model id (LiteLLM) | `bedrock/amazon.titan-embed-text-v2:0` |
| Model id (raw) | `amazon.titan-embed-text-v2:0` |
| Output dim | 1024 (default), 512, 256 |
| Max input | 8K tokens |
| Pricing | $0.02 per 1M tokens |
| Languages | 100+ (multilingual) |

Use 1024 (default). Don't reduce dim unless Qdrant storage
matters and you've measured quality impact.

### Other models we might use later

- `anthropic.claude-3-5-sonnet-20241022` on Bedrock — same
  model Bedrock hosts, same tools, possibly better at
  long-context reasoning.
- `cohere.command-r-plus-v1:0` on Bedrock — strong RAG model
  (Cohere designed it for retrieval-augmented tasks). Could be a
  future swap for the chat model.
- `amazon.nova-micro-v1:0` — for cheap classification.

---

## 3. Authentication: SigV4

Bedrock uses **AWS Signature Version 4** for auth. Every request
must be signed with your AWS access key + secret. The signing is
complex (canonical request, string to sign, derived key, HMAC) but
you don't do it by hand — the AWS SDK and LiteLLM handle it.

The credentials LiteLLM needs:

```
AWS_ACCESS_KEY_ID     = AKIA...
AWS_SECRET_ACCESS_KEY = ...
AWS_REGION            = us-east-1
```

Three ways to provide them in Strata:

1. **k8s Secret (Phase 2 and Phase 5 single-user).** Set
   `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in
   `control-plane/manifests/10-litellm/secret.yaml`. Mount as env
   vars on the LiteLLM Deployment. **Gitignored.**
2. **IAM Role for Service Accounts (IRSA, Phase 5 EKS).** The
   Strata-prod EKS cluster creates a `strata-litellm` IAM role.
   The LiteLLM ServiceAccount is annotated with
   `eks.amazonaws.com/role-arn`. The pod gets temporary creds
   from the AWS metadata service. **No static keys in the cluster.**
3. **IAM Roles Anywhere (Phase 6 cross-account).** Strata-prod
   cluster assumes a role in the customer's account. Same IRSA
   pattern but the role is in a different account. The onboarding
   CFN template creates the role.

For Phase 2 (Kind) and Phase 5 single-user (your own account),
option 1 is correct. Don't bother with IRSA in Kind — IRSA
requires real EKS.

### The cost of getting auth wrong

- `403 AccessDeniedException` — IAM policy doesn't grant
  `bedrock:InvokeModel` on the model ARN. Fix: add the policy.
- `400 ValidationException` — wrong model id or region. Fix: check
  spelling and region.
- `403 AccessDeniedException` with "Marketplace subscriptions" — the
  model is from AWS Marketplace and you haven't accepted the
  EULA. Fix: go to the Bedrock console and click "Subscribe" for
  the model.
- `403 AccessDeniedException` with "role ... cannot be assumed" —
  trust policy issue. For IRSA, the role's trust policy must list
  the cluster's OIDC provider. For cross-account, the trust policy
  must list the controller account + external ID.

### The minimum IAM policy for Strata LiteLLM

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
      ]
    }
  ]
}
```

In Phase 5's bootstrap, this lives in an IRSA role trust policy.
For Phase 2, it lives in the AWS user's IAM policy (or a temp
user created for the dev session).

---

## 4. Latency, retries, and cost

### Latency

Nova Pro first-token latency: 200–600ms. Token generation:
50–150 tokens/sec. For a 200-token response, expect ~2s total
on a warm connection.

LiteLLM's `timeout: 60` setting is generous. The Bedrock client
in LiteLLM has its own retry logic for 5xx and throttling.

### Retries and throttling

Bedrock throttles per region per account. Default quota for
`amazon.nova-pro-v1:0` in `us-east-1` is **400 requests/minute**
and **400K tokens/minute** per account. For one user
chatting with the agent, you'll never hit this. For multi-tenant
(Phase 6+), you might, and you need:

- LiteLLM `num_retries: 3` and exponential backoff.
- LiteLLM fallbacks to a different region or different model.
- Request quotas in the Kong layer (Phase 6+).

### Cost

For Phase 2 dev (1 user, dozens of messages per session):
$0.001–$0.01 per session. RAG embeddings (reindexing 100 docs):
$0.0001 per reindex. Phase 2 dev costs are negligible.

For Phase 6+ multi-tenant, budget per user is ~$0.50–$5/month
depending on usage. Strata doesn't bill users in Phase 6+;
this is just sizing.

---

## 5. Streaming

LiteLLM translates OpenAI-style streaming (`stream=True` →
server-sent events) to Bedrock's
`InvokeModelWithResponseStream` or `ConverseStream` API. The
Strata agent-service does:

```python
model = ChatOpenAI(..., streaming=True)
# LangChain's .stream() returns AIMessageChunks
```

Phase 2's `app/main.py` doesn't actually stream — it invokes
synchronously and emits the final state as NDJSON. Phase 5+
will use `astream(stream_mode="messages")` for real token
streaming. The Bedrock side is already capable; we just need
to flip the switch.

---

## 6. Working with Bedrock from your laptop (not the cluster)

For interactive debugging without spinning up the cluster:

```bash
# Install the AWS SDK and use it directly
pip install boto3

# Configure creds
aws configure   # or set AWS_ACCESS_KEY_ID etc.

# Test a model call
python -c "
import boto3, json
client = boto3.client('bedrock-runtime', region_name='us-east-1')
r = client.converse(
    modelId='amazon.nova-pro-v1:0',
    messages=[{'role': 'user', 'content': [{'text': 'hello'}]}],
)
print(r['output']['message']['content'][0]['text'])
"
```

`converse` is the modern, model-agnostic API. Use it for new code.
`invoke_model` is older, requires model-specific request schemas.

### Converse API shape

```python
client.converse(
    modelId='amazon.nova-pro-v1:0',
    messages=[
        {'role': 'user', 'content': [{'text': 'hello'}]},
        {'role': 'assistant', 'content': [{'text': 'hi!'}]},
        {'role': 'user', 'content': [{'text': 'how are you?'}]},
    ],
    system=[{'text': 'You are a friendly assistant.'}],
    inferenceConfig={'maxTokens': 512, 'temperature': 0.5},
    toolConfig={...},  # for tool calling
)
```

The `Converse` API is the AWS standard for chat models; LiteLLM
uses it for the providers that support it (Nova, Claude 3+, Mistral,
Cohere, Meta Llama 3+).

### Tool calling on Bedrock

The `toolConfig` parameter takes:

```python
toolConfig={
    'tools': [
        {
            'toolSpec': {
                'name': 'list_clusters',
                'description': 'List all EKS clusters in the user\'s account.',
                'inputSchema': {
                    'json': {
                        'type': 'object',
                        'properties': {},
                        'required': []
                    }
                }
            }
        }
    ]
}
```

The `inputSchema.json` is the same JSON Schema format that LangChain
generates from your `@tool`-decorated function. LiteLLM translates
the LangChain `BaseTool` list to this format automatically.

### Streaming with Converse

```python
response = client.converse_stream(
    modelId='amazon.nova-pro-v1:0',
    messages=[...],
)
for event in response['stream']:
    if 'contentBlockDelta' in event:
        print(event['contentBlockDelta']['delta']['text'], end='')
```

LiteLLM wraps this as OpenAI-style streaming.

---

## 7. Common pitfalls

1. **Wrong region.** Bedrock model not available in your chosen
   region. Switch region or pick a different model.
2. **Missing IAM permissions.** `bedrock:InvokeModel` is required.
   `bedrock:InvokeModelWithResponseStream` for streaming (same
   `bedrock:Invoke*` action group usually covers both).
3. **Marketplace subscription missing.** Anthropic and some other
   models require you to "Subscribe" in the Bedrock console first.
4. **Model ID syntax.** Bedrock uses `amazon.nova-pro-v1:0`, not
   `bedrock/amazon.nova-pro-v1:0` — the `bedrock/` prefix is
   LiteLLM's provider routing, NOT part of the actual model id.
   Pass `model: bedrock/amazon.nova-pro-v1:0` to LiteLLM; it
   strips the prefix and calls Bedrock with `amazon.nova-pro-v1:0`.
5. **Throttling.** Per-account, per-region, per-model. LiteLLM
   retries; you might still see latency spikes.
6. **Context window overflow.** Nova Pro's 300K window is huge.
   If you see `ValidationException: input too long`, you have a
   bug (likely an infinite loop in the agent graph).
7. **Cost surprises.** Set up a billing alarm. Even at $0.0008/1K
   input tokens, a runaway agent loop can rack up charges.
   LiteLLM doesn't enforce spend caps natively; do it in
   CloudWatch or AWS Budgets.

---

## 8. Strata's Bedrock config

**Phase 2 (Kind, single-user):**

- IAM: dev user with `bedrock:InvokeModel` and
  `bedrock:InvokeModelWithResponseStream` on both model ARNs.
- Secret: `control-plane/manifests/10-litellm/secret.yaml`
  (gitignored, copied from `.example`).
- LiteLLM model_list: Nova Pro + Titan v2 in `us-east-1`.

**Phase 5 (real EKS, single-user):**

- IAM: IRSA role for the LiteLLM ServiceAccount, scoped to
  `bedrock:Invoke*` on the two model ARNs. No static keys.
- Secret: deleted.
- Same model_list.

**Phase 6 (multi-tenant SaaS):**

- IAM: per-user rate limiting at Kong; per-user cost tracking via
  LiteLLM virtual keys.
- Bedrock: same models, but CRIS profiles for throttling
  resilience.

---

## 9. What to read next

- `docs/litellm.md` — the proxy that sits between Strata and
  Bedrock.
- `docs/rag.md` — the embedding pipeline (Titan v2).
- `docs/langchain.md` — how `ChatOpenAI` calls the proxy.
- AWS Bedrock user guide: <https://docs.aws.amazon.com/bedrock/>
- Bedrock Converse API: <https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Converse.html>
- LiteLLM Bedrock provider: <https://docs.litellm.ai/docs/providers/bedrock>
