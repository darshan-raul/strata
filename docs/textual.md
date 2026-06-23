# Textual

> **Stub for Phase 0.** Full doc lands in Phase 0 close-out or
> Phase 1.

[Textual](https://textual.textualize.io/) is the Python TUI
framework Strata uses for its terminal interface.

Why Textual:

- Pure Python (no JS / CSS — `from textual.app import App`)
- Async-first, with a worker pool for offloading sync work
  (like our LangChain / LangGraph agent loop)
- CSS-like styling for layout
- Built-in widgets (`RichLog`, `Input`, `DataTable`, `Static`)
  and modal screens (`ModalScreen`) for confirmation flows
- Rich underneath for rendering, including markup syntax

The TUI app class is `strata_tui.app.StrataTUIApp`. The
agent loop runs on a background thread via
`@work(thread=True, exclusive=True)` and uses
`call_from_thread` to push UI updates.

Planned outline:

1. The Textual mental model: App, Compose, Widgets, Screens
2. Async + workers + `call_from_thread`
3. Built-in widgets we'll use: `RichLog`, `Input`,
   `DataTable`, `Header`, `Static`, `Footer`
4. Modal screens for confirmation (Phase 3)
5. Keybindings
6. CSS / styling
7. Testing with `App.run_test`
8. What to read next