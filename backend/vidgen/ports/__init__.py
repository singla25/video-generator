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
    VoiceCloner,
)

__all__ = [
    "BatchRepository",
    "Cipher",
    "Clock",
    "LabelRenderer",
    "LipSyncer",
    "QualityChecker",
    "SheetReader",
    "SpeechToText",
    "Storage",
    "TemplateRepository",
    "TextDetector",
    "TextRenderer",
    "Transliterator",
    "VideoEncoder",
    "VoiceCloner",
]
