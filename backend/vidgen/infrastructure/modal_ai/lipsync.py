"""Lip sync on Modal is not available yet (licence decision BL-7): a clear failure, never a fake."""

from __future__ import annotations

import logging
from pathlib import Path

from vidgen.domain.codes import DomainError, FailureCode

logger = logging.getLogger(__name__)


class UnavailableLipSyncer:
    """``LipSyncer`` that always refuses, so no silent stand-in video is produced."""

    def sync(
        self,
        video: Path,
        audio: Path,
        out: Path,
        start_s: float = 0.0,
        key_from: Path | None = None,
    ) -> None:
        """Raise ``LIPSYNC_UNAVAILABLE``; nothing is written to ``out``."""
        logger.warning("lip sync requested in modal mode but it is not available")
        raise DomainError(FailureCode.LIPSYNC_UNAVAILABLE)
