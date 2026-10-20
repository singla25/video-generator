"""Start the server app (API mounted under /api) with settings from VIDGEN_* variables.

Used by run_stack.py.
"""

from __future__ import annotations

import uvicorn

from vidgen.api.server import create_server_app
from vidgen.settings import get_settings

HOST = "127.0.0.1"
PORT = 8000

if __name__ == "__main__":
    uvicorn.run(create_server_app(get_settings()), host=HOST, port=PORT, log_level="warning")
