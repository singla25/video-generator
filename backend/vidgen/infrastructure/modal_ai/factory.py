"""AI adapters for ``ai_mode == "modal"``; ``modal`` is imported only when a remote call is made."""

from __future__ import annotations

from vidgen.infrastructure.fakes import FakeTransliterator
from vidgen.infrastructure.local_ai.factory import AiAdapters
from vidgen.infrastructure.modal_ai.client import RemoteModelClient
from vidgen.infrastructure.modal_ai.lipsync import UnavailableLipSyncer
from vidgen.infrastructure.modal_ai.modal_client import ModalRemoteClient
from vidgen.infrastructure.modal_ai.stt import ModalSpeechToText
from vidgen.infrastructure.modal_ai.tts import ModalVoiceCloner
from vidgen.settings import Settings


def build_modal_adapters(settings: Settings, client: RemoteModelClient | None = None) -> AiAdapters:
    """Speech and voice on the remote app; lip sync refuses; spelling stays the fake one.

    ``client`` is for tests; by default the real client for ``settings.modal_app_name``.
    """
    remote = client if client is not None else ModalRemoteClient(settings.modal_app_name)
    return AiAdapters(
        stt=ModalSpeechToText(remote),
        transliterator=FakeTransliterator(),
        voice=ModalVoiceCloner(remote),
        lipsync=UnavailableLipSyncer(),
    )
