"""`python -m memoria.mcp` - how `.mcp.json` starts the server.

A module rather than the console script, because a module works the moment
the package is on the path while a newly added console script does not exist
until the environment is reinstalled - and this repo makes worktrees often.
"""

import sys

from memoria.mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
