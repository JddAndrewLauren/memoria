"""The FastAPI adapter, the third over the core (#64).

Same rule the MCP server (#11/#12) already keeps: domain logic stays in
``memoria.*``, this package calls it and shapes the result, and it opens no
SQLite database and no evidence file directly - see ``test_web_app.py``'s
import allowlist. ``docs/adr/0002-ui-is-a-react-client.md`` settles that this
package lives at ``src/memoria/web/`` and its consumer (``ui/``) generates
its TypeScript types from its OpenAPI schema rather than duplicating them.
"""
