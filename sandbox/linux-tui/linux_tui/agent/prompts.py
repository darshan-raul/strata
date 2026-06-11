"""ChatPromptTemplate + MessagesPlaceholder for the agent.

The structure is the canonical "I/O prompts" pattern:
  - A static SystemMessage describing the assistant.
  - A MessagesPlaceholder for the rolling conversation history.

`build_prompt()` returns a `Runnable` that can be composed with
the chat model and an output parser via `|`.
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

SYSTEM_PROMPT = """You are a Linux helper running inside a Textual TUI.

You can call the available tools to inspect the local system, read
files, search with grep, and run shell commands. When the user asks
a question:

- Prefer tool calls over guessing. If they ask "what's in /var/log?",
  call list_dir, then summarize.
- Be concise. The user is a senior engineer.
- For read-only operations, just run the tool.
- For run_command, you must be careful: the user will be asked to
  confirm any mutating or destructive command. If the user's request
  is destructive (rm, mv, chmod, kill, etc.), still call the tool —
  the TUI gates execution.
- If a tool returns an error or no output, say so plainly.

Never invent file contents or command output. If you don't know,
say you don't know and offer to run a tool to find out.
"""


def build_prompt() -> ChatPromptTemplate:
    """The agent's prompt template.

    The `messages` slot is the full conversation history (Human,
    AI, Tool messages). The system prompt is constant.
    """
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("messages"),
    ])
