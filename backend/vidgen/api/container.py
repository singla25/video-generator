"""Wires settings, adapters and services into one object held by the app."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from argon2 import PasswordHasher

from vidgen.api.client_address import Network, parse_networks
from vidgen.api.security import SessionCodec
from vidgen.infrastructure.clock import SystemClock
from vidgen.infrastructure.consent import detect_consent_type
from vidgen.infrastructure.db.uow import SqlUnitOfWork, get_engine, uow_factory
from vidgen.infrastructure.ffmpeg.probe import FfprobeVideoProbe
from vidgen.infrastructure.storage.local import LocalStorage
from vidgen.ports import Clock, SpeechToText, Storage, VideoLimits, VideoProbe
from vidgen.ports.models import TemplateRecord
from vidgen.services.audit import AuditTrail
from vidgen.services.login_guard import LoginGuard, LoginRules
from vidgen.services.templates import TemplateService
from vidgen.settings import Settings


@dataclass
class AppDeps:
    """Optional replacements for the real adapters (used by tests; ``None`` = real)."""

    clock: Clock | None = None
    speech_to_text: SpeechToText | None = None
    video_probe: VideoProbe | None = None
    storage: Storage | None = None


class _NotConfiguredSpeechToText:
    """Placeholder until the fake/real STT adapters exist (T14 / M2); analysis then fails."""

    def transcribe(self, audio: object) -> list[object]:
        raise RuntimeError("speech-to-text is not configured")


@dataclass
class Container:
    """Everything the request handlers need."""

    settings: Settings
    clock: Clock
    codec: SessionCodec
    guard: LoginGuard
    hasher: PasswordHasher
    trusted_proxies: tuple[Network, ...]
    audit: AuditTrail
    templates: TemplateService


def build_container(settings: Settings, deps: AppDeps) -> Container:
    """Create the container; refuses to start without an admin password hash."""
    if not settings.admin_password_hash.get_secret_value().strip():
        raise ValueError("admin password hash is not set")
    clock = deps.clock or SystemClock()
    factory = uow_factory(settings.database_url)
    get_engine(settings.database_url)

    def open_uow() -> SqlUnitOfWork:
        return SqlUnitOfWork(factory)

    limits = VideoLimits(
        settings.max_video_bytes, settings.max_video_seconds, settings.min_video_seconds
    )
    templates = TemplateService(
        uow=open_uow,
        storage=deps.storage or LocalStorage(settings.storage_root),
        probe=deps.video_probe or FfprobeVideoProbe(limits),
        stt=deps.speech_to_text or _NotConfiguredSpeechToText(),  # type: ignore[arg-type]
        clock=clock,
        confidence_threshold=settings.stt_confidence_threshold,
        sniff_consent=detect_consent_type,
    )
    rules = LoginRules(
        max_failures=settings.login_max_failures,
        max_failures_global=settings.login_max_failures_global,
        window=timedelta(minutes=settings.login_window_minutes),
        lockout=timedelta(minutes=settings.login_lockout_minutes),
        throttle_gap=timedelta(seconds=settings.login_throttle_seconds),
    )
    return Container(
        settings=settings,
        clock=clock,
        codec=SessionCodec(
            settings.session_secret.get_secret_value(),
            settings.session_version,
            timedelta(minutes=settings.session_ttl_minutes),
        ),
        guard=LoginGuard(rules),
        hasher=PasswordHasher(),
        trusted_proxies=parse_networks(settings.trusted_proxies),
        audit=AuditTrail(open_uow, clock),
        templates=templates,
    )


__all__ = ["AppDeps", "Container", "TemplateRecord", "build_container"]
