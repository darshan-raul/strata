"""The agent chain: `prompt | llm.bind_tools(tools)`.

This is the LangChain composition shape. The chain takes a dict
with a `messages` key, calls the LLM, and returns an `AIMessage`.
The loop in `loop.py` handles tool calls separately — the chain
itself just does the LLM call.

Why a separate `chain.py` from `loop.py`? `chain.py` is pure
LangChain composition (declarative). `loop.py` is the imperative
state machine that drives the chain and runs tools between calls.
Separating them keeps each piece testable.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from linux_tui.agent.prompts import build_prompt


def build_chain(llm: BaseChatModel, tools: list[BaseTool]) -> Runnable:
    """Build the agent's chain.

    Composition: `prompt | llm.bind_tools(tools)`. The result is a
    `Runnable` that takes a dict with `messages` and returns an
    `AIMessage`. Tool calls are surfaced as `AIMessage.tool_calls`
    in the result; the loop in `loop.py` runs them and feeds the
    `ToolMessage`s back as the next input's `messages`.
    """
    return build_prompt() | llm.bind_tools(tools)
