"""Start the API with settings from VIDGEN_* environment variables (used by run_stack.py)."""

from __future__ import annotations

import uvicorn

from vidgen.api.app import create_app
from vidgen.settings import get_settings

HOST = "127.0.0.1"
PORT = 8000

if __name__ == "__main__":
    uvicorn.run(create_app(get_settings()), host=HOST, port=PORT, log_level="warning")
