"""The Memoria MCP server: the model-facing adapter over the core.

Thin by construction (ADR-0002, ADR-0004): it resolves nothing, parses
nothing and reaches neither SQLite nor the filesystem. It calls
``memoria.records.read`` and shapes the result into text.
"""
