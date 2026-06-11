"""The agent loop — plain Python, no LangGraph.

Mirrors the canonical LangChain agent loop from
`docs/langchain/01-mental-model.md` §4:
    1. Prepend a system message to the messages.
    2. Call the model.
    3. If the response has tool_calls, run them, build ToolMessages,
       append to messages, go to 2.
    4. Otherwise return the final AI message.

`run_turn` runs ONE turn (one user message + however many
model/tool iterations it takes to reach a final answer). The
TUI calls `run_turn` for each user input.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from linux_tui.tools import MUTATING_TOOLS

log = logging.getLogger("linux-tui.agent")

# Maximum iterations to prevent runaway loops. Default 10 is generous
# for a Linux helper (most queries take 1-3 tool calls).
MAX_ITERATIONS = 10


def _serialize_tool_result(result: Any) -> str:
    """Turn a tool return value into the string the model sees.

    ToolMessage.content is always a string. If a tool returns a
    dict or list, serialize to JSON; if a primitive, str() it.
    """
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, default=str, indent=2)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def _format_tool_call(tc: Any) -> str:
    """Format a tool call for human-readable display."""
    name = tc.get("name", "?")
    args = tc.get("args", {})
    args_str = json.dumps(args, default=str) if args else "{}"
    return f"{name}({args_str})"


def run_turn(
    chain: Runnable,
    tools_by_name: dict[str, BaseTool],
    user_message: str,
    history: list | None = None,
    *,
    on_tool_call: Callable[[str, dict], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    on_iteration: Callable[[int], None] | None = None,
    is_mutating_allowed: Callable[[str, dict], bool] | None = None,
) -> tuple[list, AIMessage]:
    """Run one user turn through the agent loop.

    Args:
        chain: The composed `prompt | llm.bind_tools(tools)` Runnable.
        tools_by_name: Map of tool name -> BaseTool, for tool execution.
        user_message: The user's input string.
        history: Prior conversation messages (Human/AI/Tool). If None,
            starts fresh.
        on_tool_call: Optional callback invoked with (name, args)
            BEFORE the tool runs. Useful for "show this in the TUI."
        on_tool_result: Optional callback invoked with (name, content)
            AFTER the tool returns. Useful for "show the result."
        on_iteration: Optional callback invoked with the iteration
            number (1-based) at the start of each LLM call.
        is_mutating_allowed: Optional gate. Called with (name, args)
            before any tool runs; if it returns False, the tool is
            NOT executed and the model gets a refusal ToolMessage.

    Returns:
        (messages, final_ai_message):
            - messages: the full new message list (history + new turns).
              The caller can use this to update its history.
            - final_ai_message: the last AIMessage in the list (the
              assistant's final answer to the user).
    """
    messages: list = list(history or [])

    # System message is added by the prompt template; we don't need
    # to inject it here. Just append the user's message.
    messages.append(HumanMessage(content=user_message))

    iteration = 0
    while iteration < MAX_ITERATIONS:
        iteration += 1
        if on_iteration:
            on_iteration(iteration)

        log.debug("iteration %d: invoking model with %d messages", iteration, len(messages))
        response: AIMessage = chain.invoke({"messages": messages})

        # If the model didn't call any tool, we're done.
        if not response.tool_calls:
            messages.append(response)
            return messages, response

        # Otherwise, run each tool call and append the resulting
        # ToolMessages.
        messages.append(response)
        for tc in response.tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            tool_call_id = tc.get("id", "")

            if on_tool_call:
                on_tool_call(name, args)

            # Mutating-tool gate. If the TUI hasn't approved, we
            # tell the model the call was refused and let it react.
            if name in MUTATING_TOOLS:
                if is_mutating_allowed is not None and not is_mutating_allowed(name, args):
                    log.info("mutating tool %s denied by user", name)
                    refusal = ToolMessage(
                        content=(
                            f"REFUSED by user: the command {args.get('cmd', '')!r} was not "
                            f"approved. The user must approve mutating commands before "
                            f"they run. Ask the user to confirm or suggest a different "
                            f"approach."
                        ),
                        name=name,
                        tool_call_id=tool_call_id,
                        status="error",
                    )
                    messages.append(refusal)
                    if on_tool_result:
                        on_tool_result(name, refusal.content)
                    continue

            tool = tools_by_name.get(name)
            if tool is None:
                err = ToolMessage(
                    content=f"UNKNOWN_TOOL: no tool named {name!r}",
                    name=name,
                    tool_call_id=tool_call_id,
                    status="error",
                )
                messages.append(err)
                if on_tool_result:
                    on_tool_result(name, err.content)
                continue

            try:
                result = tool.invoke(args)
                content = _serialize_tool_result(result)
                tm = ToolMessage(content=content, name=name, tool_call_id=tool_call_id)
            except Exception as e:
                log.exception("tool %s failed", name)
                tm = ToolMessage(
                    content=f"ERROR: {type(e).__name__}: {e}",
                    name=name,
                    tool_call_id=tool_call_id,
                    status="error",
                )

            messages.append(tm)
            if on_tool_result:
                on_tool_result(name, tm.content)

    # If we got here, the loop hit MAX_ITERATIONS without converging.
    # Append a final message explaining so the user sees something.
    last_ai = messages[-1] if isinstance(messages[-1], AIMessage) else None
    if last_ai is None or last_ai.tool_calls:
        # Last message was a tool result; ask the model to summarize.
        try:
            response = chain.invoke({"messages": messages})
        except Exception as e:
            log.exception("final summary call failed")
            response = AIMessage(content=f"[agent loop ended: {e}]")
    else:
        response = last_ai
    messages.append(response)
    return messages, response


def tools_to_dict(tools: Iterable[BaseTool]) -> dict[str, BaseTool]:
    """Map tool name -> tool object. Used by the loop to dispatch."""
    return {t.name: t for t in tools}
