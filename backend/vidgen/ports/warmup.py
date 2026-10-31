"""Port for local models that can be loaded at worker start and released again (T-PROG-BE).

Pure Protocol: no I/O and no framework imports.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Warmable(Protocol):
    """A model adapter that can load its weights up front and free them afterwards."""

    def warm_up(self) -> None:
        """Load the model now so broken or missing weights fail at start-up."""
        ...

    def release(self) -> None:
        """Free the model's memory; it loads again on the next use."""
        ...
