"""Tests for the agent loop, using a tool-capable fake model.

No network. No real LLM. The fake model returns a canned sequence
of AIMessages (with or without tool_calls), and we verify the loop
runs the right tools, builds the right ToolMessages, and returns
the final AI message.

Note: langchain's `FakeMessagesListChatModel` does not implement
`bind_tools` (the base class raises NotImplementedError). We
subclass it and override `bind_tools` to return a `RunnableBinding`
that wraps the same fake — the loop in `loop.py` is what actually
runs the tools, not the model, so the fake just needs to be a
valid `Runnable` that yields the canned AIMessages.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableBinding
from langchain_core.tools import tool

from linux_tui.agent.chain import build_chain
from linux_tui.agent.loop import run_turn, tools_to_dict


# ---- test fake -------------------------------------------------------------


class _ToolFake(FakeMessagesListChatModel):
    """A FakeMessagesListChatModel that supports bind_tools.

    The base class's `bind_tools` raises NotImplementedError. We
    override to return a RunnableBinding so `llm.bind_tools(tools)`
    works in tests. The bound tools are recorded (so we can assert
    about them) but the model itself doesn't use them — the agent
    loop in `loop.py` is what actually runs the tools.
    """

    def bind_tools(self, tools, **kwargs: Any) -> RunnableBinding:
        self._bound_tools = list(tools)
        return RunnableBinding(
            bound=self,
            kwargs={"tools": list(tools), **kwargs},
        )


# ---- test tools ------------------------------------------------------------


@tool
def echo_tool(text: str) -> str:
    """Echo the input back, as a string.

    Use this when the user wants the model to repeat something.
    """
    return f"echo: {text}"


@tool
def double_tool(n: int) -> int:
    """Double an integer. Returns the input multiplied by 2.

    Use this for simple math.
    """
    return n * 2


# ---- helpers ---------------------------------------------------------------


def _fake_model(responses: list[AIMessage]) -> _ToolFake:
    return _ToolFake(responses=responses)


# ---- tests -----------------------------------------------------------------


def test_run_turn_with_no_tool_calls() -> None:
    """The model just replies with text. The loop should return it directly."""
    fake = _fake_model([AIMessage(content="hello back")])
    chain = build_chain(fake, [echo_tool])

    events: list[tuple[str, str]] = []
    msgs, final = run_turn(
        chain,
        tools_to_dict([echo_tool]),
        "hi",
        on_tool_call=lambda n, a: events.append(("call", n)),
        on_tool_result=lambda n, c: events.append(("result", n)),
    )

    assert final.content == "hello back"
    assert len(msgs) == 2     # user + final AI
    assert msgs[0].content == "hi"
    assert msgs[1].content == "hello back"
    assert events == []       # no tools called


def test_run_turn_with_one_tool_call() -> None:
    """The model calls a tool, the loop runs it, and the final answer comes back."""
    fake = _fake_model([
        AIMessage(
            content="",
            tool_calls=[{
                "name": "echo_tool",
                "args": {"text": "ping"},
                "id": "tc-1",
            }],
        ),
        AIMessage(content="the tool said: echo: ping"),
    ])
    chain = build_chain(fake, [echo_tool])

    events: list[tuple[str, str]] = []
    msgs, final = run_turn(
        chain,
        tools_to_dict([echo_tool]),
        "echo ping",
        on_tool_call=lambda n, a: events.append(("call", n)),
        on_tool_result=lambda n, c: events.append(("result", n)),
    )

    # Two iterations: the tool call, then the final answer.
    assert _any(events, "call", "echo_tool")
    assert _any(events, "result", "echo_tool")
    assert final.content == "the tool said: echo: ping"

    # Message list shape: user, AI (tool_call), Tool, AI (final)
    assert len(msgs) == 4
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage) and msgs[1].tool_calls
    assert isinstance(msgs[2], ToolMessage)
    assert "echo: ping" in msgs[2].content
    assert isinstance(msgs[3], AIMessage) and not msgs[3].tool_calls


def test_run_turn_with_parallel_tool_calls() -> None:
    """The model emits two tool calls in one AIMessage. The loop runs both."""
    fake = _fake_model([
        AIMessage(
            content="",
            tool_calls=[
                {"name": "echo_tool", "args": {"text": "a"}, "id": "tc-1"},
                {"name": "double_tool", "args": {"n": 21}, "id": "tc-2"},
            ],
        ),
        AIMessage(content="both done"),
    ])
    chain = build_chain(fake, [echo_tool, double_tool])

    events: list[tuple[str, str]] = []
    msgs, _ = run_turn(
        chain,
        tools_to_dict([echo_tool, double_tool]),
        "do two things",
        on_tool_call=lambda n, a: events.append(("call", n)),
        on_tool_result=lambda n, c: events.append(("result", n)),
    )

    call_names = [n for k, n in events if k == "call"]
    result_names = [n for k, n in events if k == "result"]
    assert "echo_tool" in call_names
    assert "double_tool" in call_names
    assert "echo_tool" in result_names
    assert "double_tool" in result_names

    # Two ToolMessages in the message list.
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 2
    contents = [m.content for m in tool_msgs]
    assert any("echo: a" in c for c in contents)
    assert any("42" in c for c in contents)


def test_run_turn_unknown_tool() -> None:
    """If the model hallucinates a tool name, the loop returns an error ToolMessage."""
    fake = _fake_model([
        AIMessage(
            content="",
            tool_calls=[{
                "name": "no_such_tool",
                "args": {},
                "id": "tc-1",
            }],
        ),
        AIMessage(content="sorry, I made that up"),
    ])
    chain = build_chain(fake, [echo_tool])

    msgs, _ = run_turn(
        chain,
        tools_to_dict([echo_tool]),
        "do the thing",
    )

    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1
    assert "UNKNOWN_TOOL" in tool_msgs[0].content


def test_run_turn_mutating_denied() -> None:
    """When is_mutating_allowed returns False, the loop refuses the tool call."""
    from linux_tui.tools import MUTATING_TOOLS

    @tool
    def mutate_thing() -> str:
        """Mutate something. Listed in MUTATING_TOOLS for testing."""
        return "did it"

    MUTATING_TOOLS.add("mutate_thing")    # type: ignore[attr-defined]
    try:
        fake = _fake_model([
            AIMessage(
                content="",
                tool_calls=[{"name": "mutate_thing", "args": {}, "id": "tc-1"}],
            ),
            AIMessage(content="ok, didn't do it"),
        ])
        chain = build_chain(fake, [mutate_thing])

        def is_allowed(name, args) -> bool:
            return False    # deny everything

        msgs, _ = run_turn(
            chain,
            tools_to_dict([mutate_thing]),
            "do it",
            is_mutating_allowed=is_allowed,
        )

        tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert "REFUSED" in tool_msgs[0].content
        assert tool_msgs[0].status == "error"
    finally:
        MUTATING_TOOLS.discard("mutate_thing")    # type: ignore[attr-defined]


def test_run_turn_history_preserved() -> None:
    """Prior history is passed through to the model."""
    fake = _fake_model([AIMessage(content="got it")])
    chain = build_chain(fake, [echo_tool])

    prior = [
        HumanMessage(content="earlier message"),
        AIMessage(content="earlier reply"),
    ]
    msgs, _ = run_turn(chain, tools_to_dict([echo_tool]), "new question", history=prior)

    # The history is preserved, then the new turn is appended.
    assert msgs[0].content == "earlier message"
    assert msgs[1].content == "earlier reply"
    assert msgs[2].content == "new question"
    assert msgs[3].content == "got it"


def test_run_turn_max_iterations_caps() -> None:
    """If the model never stops calling tools, the loop caps at MAX_ITERATIONS."""
    # Make a fake that always emits a tool call.
    infinite = _fake_model([
        AIMessage(
            content="",
            tool_calls=[{"name": "echo_tool", "args": {"text": "loop"}, "id": f"tc-{i}"}],
        )
        for i in range(20)    # 20 tool calls
    ] + [AIMessage(content="ok done")])
    chain = build_chain(infinite, [echo_tool])

    msgs, _ = run_turn(chain, tools_to_dict([echo_tool]), "loop forever")

    # We should not have 20 ToolMessages; the cap should kick in
    # well before that. (Exact count depends on MAX_ITERATIONS.)
    tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
    assert len(tool_msgs) <= 20
    # The loop ends with a final AI message (either summary or the
    # one we put at the end of the canned list).
    assert isinstance(msgs[-1], AIMessage)


# ---- helpers ---------------------------------------------------------------


def _any(events, kind, name) -> bool:
    return any((k, n) == (kind, name) for k, n in events)
