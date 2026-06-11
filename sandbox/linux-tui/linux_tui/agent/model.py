"""Chat model factory: `ChatOpenAI` pointed at MiniMax.

MiniMax exposes an OpenAI-compatible Chat Completions API. We use
LangChain's `ChatOpenAI` with a custom `base_url` and `api_key`.
This is the same pattern Strata's `litellm_provider.py` uses, but
without the LiteLLM proxy in the middle — we talk to MiniMax
directly.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Load .env from the project root (sandbox/linux-tui/.env).
load_dotenv()


def build_chat_model(
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    streaming: bool = True,
) -> ChatOpenAI:
    """Build the LangChain chat model that talks to MiniMax.

    All kwargs default to env vars. The `streaming=True` default is
    what the TUI wants so tokens can be pushed to the UI as they
    arrive.
    """
    base_url = base_url or os.environ.get("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
    api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
    model = model or os.environ.get("MINIMAX_MODEL", "MiniMax-M3")
    temperature = (
        temperature if temperature is not None
        else float(os.environ.get("TEMPERATURE", "0.2"))
    )
    max_tokens = (
        max_tokens if max_tokens is not None
        else int(os.environ.get("MAX_TOKENS", "2048"))
    )

    if not api_key:
        raise RuntimeError(
            "MINIMAX_API_KEY is not set. Copy .env.example to .env and fill it in."
        )

    return ChatOpenAI(
        model=model,
        base_url=f"{base_url.rstrip('/')}/v1" if not base_url.rstrip("/").endswith("/v1") else base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        streaming=streaming,
    )
