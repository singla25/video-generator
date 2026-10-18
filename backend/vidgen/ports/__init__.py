"""Port interfaces (Protocols) that services depend on."""

from vidgen.ports.interfaces import (
    BatchRepository,
    Cipher,
    Clock,
    LabelRenderer,
    LipSyncer,
    QualityChecker,
    SheetReader,
    SpeechToText,
    Storage,
    TemplateRepository,
    TextDetector,
    TextRenderer,
    Transliterator,
    VideoEncoder,
    VideoProbe,
    VoiceCloner,
)
from vidgen.ports.models import SheetRow, VideoInfo, VideoLimits

__all__ = [
    "BatchRepository",
    "Cipher",
    "Clock",
    "LabelRenderer",
    "LipSyncer",
    "QualityChecker",
    "SheetReader",
    "SheetRow",
    "SpeechToText",
    "Storage",
    "TemplateRepository",
    "TextDetector",
    "TextRenderer",
    "Transliterator",
    "VideoEncoder",
    "VideoInfo",
    "VideoLimits",
    "VideoProbe",
    "VoiceCloner",
]
