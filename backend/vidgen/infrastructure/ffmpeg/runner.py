"""Runs ffmpeg/ffprobe with an argument list, a timeout and no pipes (ADR-004).

Output goes to temporary files rather than pipes: if a killed tool left a child process
behind, a pipe would keep ``subprocess`` waiting for it.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vidgen.domain.codes import DomainError, FailureCode

logger = logging.getLogger(__name__)

_TEXT_ERRORS = "replace"


@dataclass(frozen=True)
class ToolOutput:
    """Captured text output of a finished tool."""

    stdout: str
    stderr: str


def run_tool(args: list[str], timeout_seconds: float) -> ToolOutput:
    """Run ``args`` (no shell). Timeout -> RENDER_TIMEOUT; any other failure -> INTERNAL_ERROR."""
    tool = Path(args[0]).name
    with tempfile.TemporaryFile() as out_file, tempfile.TemporaryFile() as err_file:
        try:
            result = subprocess.run(  # noqa: S603 - argument list, never a shell
                args,
                stdin=subprocess.DEVNULL,
                stdout=out_file,
                stderr=err_file,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            logger.error("media tool timed out", extra={"tool": tool})
            raise DomainError(FailureCode.RENDER_TIMEOUT) from exc
        except OSError as exc:
            logger.error("media tool could not start", extra={"tool": tool})
            raise DomainError(FailureCode.INTERNAL_ERROR) from exc
        if result.returncode != 0:
            logger.error("media tool failed", extra={"tool": tool, "returncode": result.returncode})
            raise DomainError(FailureCode.INTERNAL_ERROR)
        out_file.seek(0)
        err_file.seek(0)
        return ToolOutput(
            out_file.read().decode(errors=_TEXT_ERRORS), err_file.read().decode(errors=_TEXT_ERRORS)
        )
