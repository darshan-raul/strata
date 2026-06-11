# linux-tui

Adhoc scratchpad: a Textual TUI that talks to a Linux box through
LangChain tools, using MiniMax (M3) over its OpenAI-compatible
endpoint.

**Not part of the Strata plan.** This lives under `sandbox/` and
is fully self-contained. No edits to AGENTS.md, handoff.md, or
anything else in the parent repo.

## What it does

A REPL-style TUI where you ask natural-language questions about
your local Linux box. The model has access to:

- `list_dir(path)` — directory listing
- `read_file(path, max_lines)` — file head/tail
- `grep(pattern, path, recursive)` — ripgrep-backed search
- `system_info()` — `uname`, hostname, OS
- `disk_usage(path)` — `df`-style sizes
- `run_command(cmd)` — **mutating; requires in-TUI confirmation**

`run_command` is the only mutating tool. It pops a `ModalScreen`
prompt and only runs if you confirm.

## Stack

- **TUI:** [Textual](https://textual.textualize.io/)
- **LLM plumbing:** LangChain (`langchain-core` + `langchain-openai`)
  with `ChatPromptTemplate` + `MessagesPlaceholder` +
  `StrOutputParser`
- **Model endpoint:** MiniMax M3 via `ChatOpenAI(base_url=..., api_key=...)`
  — direct OpenAI-compatible call, no proxy, no LangGraph

The agent loop is a plain Python `while True` (no `StateGraph`).
This is on purpose: the user asked for "only uses langchain."

## Run

```bash
cd sandbox/linux-tui
uv sync
cp .env.example .env       # then edit .env, set MINIMAX_API_KEY
uv run python -m linux_tui
```

Keybindings inside the TUI:

- `Enter` — send
- `Ctrl+C` — quit
- `Ctrl+L` — clear history
- `Ctrl+R` — toggle raw/parsed output (debug)

## Test

```bash
cd sandbox/linux-tui
uv run pytest
```

Tests use `FakeMessagesListChatModel` — no network, no real LLM.

## Cleanup

The whole thing is one directory. To remove:

```bash
git rm -r sandbox/linux-tui
```

No other files were touched.
