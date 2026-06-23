"""Tests for the strata-tui scratchpad.

This package contains the pytest suite for the project. Three
test files, 32 tests total:

- :mod:`test_prompts` — 4 tests for the prompt template.
- :mod:`test_tools` — 18 tests for the tool implementations
  (each tool has 1–5 tests covering shape, errors, and
  edge cases).
- :mod:`test_loop` — 7 tests for the agent loop, using a
  fake model so no real LLM is called.

The test discovery is configured in :file:`pyproject.toml`
under ``[tool.pytest.ini_options]``.

Running
-------
::

    cd sandbox/strata-tui
    uv run pytest

The tests don't need any env vars or a running LLM. The
``_ToolFake`` class in ``test_loop.py`` stands in for a real
``ChatOpenAI``.
"""
