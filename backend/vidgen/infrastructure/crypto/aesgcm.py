"""AES-256-GCM encryption with key ids, and an HMAC-SHA256 blind index (AC17, ADR-005).

Stored layout: ``[key-id length: 1 byte][key id][nonce: 12][ciphertext + tag]``. The key id is
also authenticated data, so changing it is detected. No error message contains key material
or plaintext.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vidgen.domain.naming import id_key

KEY_BYTES = 32
MIN_INDEX_KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
MAX_KEY_ID_BYTES = 255  # the length prefix is one byte
_ENCODING = "utf-8"


class DecryptionError(Exception):
    """A value could not be decrypted: wrong or unknown key, or damaged data."""

    def __init__(self) -> None:
        super().__init__("value could not be decrypted")


class AesGcmCipher:
    """Encrypts text with the active key and decrypts with any configured key."""

    def __init__(self, *, keys: Mapping[str, bytes], active_key_id: str, index_key: bytes) -> None:
        for key_id, key in keys.items():
            if len(key) != KEY_BYTES:
                raise ValueError(f"encryption key '{key_id}' must be exactly {KEY_BYTES} bytes")
            if not 0 < len(key_id.encode(_ENCODING)) <= MAX_KEY_ID_BYTES:
                raise ValueError("key id must be 1-255 bytes")
        if len(index_key) < MIN_INDEX_KEY_BYTES:
            raise ValueError(f"index key must be at least {MIN_INDEX_KEY_BYTES} bytes")
        if active_key_id not in keys:
            raise ValueError(f"active key id '{active_key_id}' is not in the key set")
        self._aead = {key_id: AESGCM(key) for key_id, key in keys.items()}
        self._active = active_key_id
        self._index_key = index_key

    def __repr__(self) -> str:
        return f"AesGcmCipher(active_key_id={self._active!r})"

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt ``plaintext`` under the active key with a fresh random nonce."""
        key_id = self._active.encode(_ENCODING)
        nonce = os.urandom(NONCE_BYTES)
        body = self._aead[self._active].encrypt(nonce, plaintext.encode(_ENCODING), key_id)
        return bytes([len(key_id)]) + key_id + nonce + body

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt a value written by ``encrypt``; any problem raises DecryptionError."""
        key_id, nonce, body = self._split(ciphertext)
        aead = self._aead.get(key_id)
        if aead is None:
            raise DecryptionError
        try:
            return aead.decrypt(nonce, body, key_id.encode(_ENCODING)).decode(_ENCODING)
        except (InvalidTag, UnicodeDecodeError) as exc:
            raise DecryptionError from exc

    def key_id_of(self, ciphertext: bytes) -> str:
        """Return the id of the key a value was encrypted with."""
        return self._split(ciphertext)[0]

    def blind_index(self, value: str) -> str:
        """Keyed, deterministic hex digest of the normalised ID, for equality search."""
        digest = hmac.new(self._index_key, id_key(value).encode(_ENCODING), hashlib.sha256)
        return digest.hexdigest()

    @staticmethod
    def _split(blob: bytes) -> tuple[str, bytes, bytes]:
        """Split a stored value into (key id, nonce, ciphertext+tag)."""
        if not blob:
            raise DecryptionError
        id_end = 1 + blob[0]
        if len(blob) < id_end + NONCE_BYTES + TAG_BYTES:
            raise DecryptionError
        try:
            key_id = blob[1:id_end].decode(_ENCODING)
        except UnicodeDecodeError as exc:
            raise DecryptionError from exc
        return key_id, blob[id_end : id_end + NONCE_BYTES], blob[id_end + NONCE_BYTES :]


if TYPE_CHECKING:  # pragma: no cover
    from vidgen.ports import Cipher

    def _satisfies_port(adapter: AesGcmCipher) -> Cipher:
        return adapter
