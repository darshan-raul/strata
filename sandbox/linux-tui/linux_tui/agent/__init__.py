"""Agent loop: prompt assembly, tool execution, plain Python (no LangGraph).

Honors the "only uses langchain" constraint. The loop is a manual
state machine: while the model emits tool calls, run them and feed
results back. No `StateGraph`, no checkpointer, no `interrupt()`.
"""
