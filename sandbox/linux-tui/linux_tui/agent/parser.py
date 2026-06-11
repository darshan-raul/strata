"""Output parsers.

`StrOutputParser` for the default text-only path. `PydanticOutputParser`
is available for callers that want a structured response (not used
by the default TUI loop, but kept for symmetry with the LangChain
docs).
"""
from __future__ import annotations

from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser

__all__ = ["StrOutputParser", "PydanticOutputParser"]
