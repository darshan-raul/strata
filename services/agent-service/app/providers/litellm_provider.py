"""LiteLLM provider.

Phase 2: thin wrapper over the OpenAI-compatible Chat Completions API
that LiteLLM exposes at `http://litellm:4000/v1`. We use
`langchain_openai.ChatOpenAI` pointed at the LiteLLM base URL — that
gives us streaming, tool-calling, and LangGraph integration for free,
without us importing a vendor SDK directly. LiteLLM handles the actual
model call (Bedrock, OpenAI, Anthropic, Ollama) under the hood.
"""
from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


def get_chat_model() -> ChatOpenAI:
    """Build the LangChain chat model that talks to LiteLLM.

    LiteLLM is OpenAI-compatible. We swap the base URL and use the
    master key for auth. The model name is whatever was registered in
    the LiteLLM `model_list` ConfigMap (e.g. `nova-pro`, `titan-embed-v2`).
    """
    base_url = os.environ.get("LITELLM_BASE_URL", "http://litellm:4000")
    api_key = os.environ.get("LITELLM_API_KEY", "sk-dev")
    model_name = os.environ.get("MODEL_NAME", "nova-pro")

    return ChatOpenAI(
        model=model_name,
        base_url=f"{base_url}/v1",
        api_key=api_key,
        temperature=0.2,
        streaming=True,
    )
