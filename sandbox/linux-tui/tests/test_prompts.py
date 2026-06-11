"""Tests for prompt assembly."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from linux_tui.agent.prompts import SYSTEM_PROMPT, build_prompt


def test_prompt_has_system_and_placeholder() -> None:
    """The prompt should have a system message and a messages placeholder."""
    p = build_prompt()
    # Inspect the input variables.
    assert "messages" in p.input_variables


def test_prompt_system_text_matches() -> None:
    """The system prompt content should match the constant."""
    assert "Linux helper" in SYSTEM_PROMPT
    assert "tool" in SYSTEM_PROMPT.lower()


def test_prompt_renders_with_history() -> None:
    """Prompt should accept a messages list and produce a PromptValue."""
    from langchain_core.messages import HumanMessage

    p = build_prompt()
    formatted = p.invoke({"messages": [HumanMessage(content="hi")]})
    # formatted is a PromptValue; convert to messages to inspect.
    msgs = formatted.to_messages()
    assert len(msgs) == 2
    assert msgs[0].content == SYSTEM_PROMPT
    assert msgs[1].content == "hi"


def test_prompt_preserves_tool_messages() -> None:
    """Tool messages in the history should be passed through."""
    from langchain_core.messages import ToolMessage

    p = build_prompt()
    history = [
        HumanMessage(content="what's in /tmp?"),
        AIMessage(content="", tool_calls=[{
            "name": "list_dir", "args": {"path": "/tmp"}, "id": "tc-1",
        }]),
        ToolMessage(content="f foo\nf bar", name="list_dir", tool_call_id="tc-1"),
    ]
    formatted = p.invoke({"messages": history})
    msgs = formatted.to_messages()
    assert len(msgs) == 4
    assert msgs[2].tool_calls  # the AI's tool call
    assert msgs[3].content == "f foo\nf bar"
