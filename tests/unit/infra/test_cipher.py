"""AES-256-GCM cipher with key ids and HMAC-SHA256 blind index (AC17, ADR-005)."""

from __future__ import annotations

import hashlib
import hmac
import secrets

import pytest

from vidgen.domain.naming import id_key
from vidgen.infrastructure.crypto.aesgcm import AesGcmCipher, DecryptionError

DEV_NAME = "राजेश कुमार"


def new_key() -> bytes:
    """A fresh random 32-byte key (never a real secret)."""
    return secrets.token_bytes(32)


@pytest.fixture
def keys() -> dict[str, bytes]:
    """Encryption keys by key id."""
    return {"k1": new_key()}


@pytest.fixture
def index_key() -> bytes:
    """Blind-index key, separate from the encryption key."""
    return new_key()


@pytest.fixture
def cipher(keys: dict[str, bytes], index_key: bytes) -> AesGcmCipher:
    """A cipher with one active key."""
    return AesGcmCipher(keys=keys, active_key_id="k1", index_key=index_key)


# ---- positive -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Rajesh Kumar", DEV_NAME, "RJ/12/097/183866", "A" * 40, "x", "a\x00b", "Smt. सुनीता"],
)
def test_encrypt_decrypt_round_trip(cipher: AesGcmCipher, text: str) -> None:
    """TT-AC17-P1, E3."""
    assert cipher.decrypt(cipher.encrypt(text)) == text


def test_empty_string_round_trips(cipher: AesGcmCipher) -> None:
    """TT-AC17-E3: empty text is allowed (optional spoken name)."""
    assert cipher.decrypt(cipher.encrypt("")) == ""


def test_one_megabyte_value_round_trips(cipher: AesGcmCipher) -> None:
    """TT-AC17-E3."""
    text = "n" * (1024 * 1024)
    assert cipher.decrypt(cipher.encrypt(text)) == text


def test_ciphertext_is_bytes_and_hides_the_plaintext(cipher: AesGcmCipher) -> None:
    """TT-AC17-P2: no plaintext (UTF-8) appears inside the stored bytes."""
    for text in ("Rajesh Kumar", DEV_NAME, "RJ/12/097/183866"):
        blob = cipher.encrypt(text)
        assert isinstance(blob, bytes)
        assert text.encode("utf-8") not in blob


def test_blind_index_is_hmac_sha256_of_the_normalised_id(
    cipher: AesGcmCipher, index_key: bytes
) -> None:
    """TT-AC17-P3 (ADR-005): hex digest of HMAC-SHA256(index_key, id_key(value))."""
    expected = hmac.new(index_key, id_key("RJ/12/097").encode("utf-8"), hashlib.sha256).hexdigest()
    assert cipher.blind_index("RJ/12/097") == expected
    assert len(expected) == 64


def test_blind_index_is_deterministic(cipher: AesGcmCipher) -> None:
    """TT-AC17-P3."""
    assert cipher.blind_index("A1") == cipher.blind_index("A1")


def test_blind_index_differs_for_different_ids(cipher: AesGcmCipher) -> None:
    """TT-AC17-P3."""
    assert cipher.blind_index("RJ12") != cipher.blind_index("RJ012")


def test_blind_index_uses_the_domain_duplicate_normalisation(cipher: AesGcmCipher) -> None:
    """TT-AC17-E4 (A2): trim, casefold and file-name sanitising before hashing."""
    assert cipher.blind_index("RJ/12/097") == cipher.blind_index(" rj_12_097 ")
    assert cipher.blind_index("A/1") == cipher.blind_index("A_1")


def test_blind_index_does_not_contain_the_plaintext_or_a_plain_hash(
    cipher: AesGcmCipher,
) -> None:
    """TT-AC17-P3: it is keyed, so it must not equal an unkeyed SHA-256."""
    value = "183866"
    index = cipher.blind_index(value)
    assert value not in index
    assert index != hashlib.sha256(id_key(value).encode()).hexdigest()


# ---- negative -------------------------------------------------------------------------


def test_wrong_key_raises_decryption_error(cipher: AesGcmCipher, index_key: bytes) -> None:
    """TT-AC17-N1."""
    blob = cipher.encrypt("Rajesh Kumar")
    other = AesGcmCipher(keys={"k1": new_key()}, active_key_id="k1", index_key=index_key)
    with pytest.raises(DecryptionError):
        other.decrypt(blob)


def test_unknown_key_id_raises_decryption_error(cipher: AesGcmCipher, index_key: bytes) -> None:
    """TT-AC17-N1: ciphertext written under a key id the reader does not have."""
    blob = cipher.encrypt("Rajesh Kumar")
    other = AesGcmCipher(keys={"k9": new_key()}, active_key_id="k9", index_key=index_key)
    with pytest.raises(DecryptionError):
        other.decrypt(blob)


def test_every_single_byte_tampering_is_detected(cipher: AesGcmCipher) -> None:
    """TT-AC17-N2: flipping any one byte (key id, nonce, body or tag) must fail."""
    blob = cipher.encrypt("Rajesh Kumar")
    for position in range(len(blob)):
        tampered = bytearray(blob)
        tampered[position] ^= 0x01
        with pytest.raises(DecryptionError):
            cipher.decrypt(bytes(tampered))


@pytest.mark.parametrize("cut", [0, 1, 5, 12])
def test_truncated_or_empty_ciphertext_raises_decryption_error(
    cipher: AesGcmCipher, cut: int
) -> None:
    """TT-AC17-N2."""
    blob = cipher.encrypt("Rajesh Kumar")
    with pytest.raises(DecryptionError):
        cipher.decrypt(blob[:cut])


def test_appended_bytes_are_detected(cipher: AesGcmCipher) -> None:
    """TT-AC17-N2."""
    with pytest.raises(DecryptionError):
        cipher.decrypt(cipher.encrypt("Rajesh Kumar") + b"\x00")


@pytest.mark.parametrize("size", [0, 1, 16, 24, 31, 33, 64])
def test_encryption_keys_must_be_exactly_32_bytes(size: int, index_key: bytes) -> None:
    """TT-AC17-N3: AES-256 needs a 32-byte key."""
    with pytest.raises(ValueError, match="32"):
        AesGcmCipher(keys={"k1": b"k" * size}, active_key_id="k1", index_key=index_key)


@pytest.mark.parametrize("size", [0, 8, 31])
def test_index_key_must_be_at_least_32_bytes(size: int, keys: dict[str, bytes]) -> None:
    """TT-AC17-N3."""
    with pytest.raises(ValueError, match="index"):
        AesGcmCipher(keys=keys, active_key_id="k1", index_key=b"i" * size)


def test_active_key_id_must_exist_in_the_key_set(index_key: bytes) -> None:
    """TT-AC17-N3."""
    with pytest.raises(ValueError, match="k2"):
        AesGcmCipher(keys={"k1": new_key()}, active_key_id="k2", index_key=index_key)


def test_repr_and_str_never_reveal_key_material(
    cipher: AesGcmCipher, keys: dict[str, bytes], index_key: bytes
) -> None:
    """TT-AC17-N3: keys must not leak through logging or tracebacks."""
    text = repr(cipher) + str(cipher)
    for secret in (keys["k1"], index_key):
        assert secret.hex() not in text
        assert repr(secret) not in text


# ---- edge -----------------------------------------------------------------------------


def test_same_plaintext_encrypts_differently_every_time(cipher: AesGcmCipher) -> None:
    """TT-AC17-E1: random nonce, 10,000 encryptions all distinct."""
    blobs = {cipher.encrypt("Rajesh Kumar") for _ in range(10_000)}
    assert len(blobs) == 10_000


def test_key_id_is_recoverable_from_the_ciphertext(cipher: AesGcmCipher) -> None:
    """TT-AC17-E2 (ADR-005): the key id travels with the value."""
    assert cipher.key_id_of(cipher.encrypt("x")) == "k1"


def test_key_rotation_old_values_still_decrypt_and_new_ones_use_the_new_key(
    index_key: bytes,
) -> None:
    """TT-AC17-E2."""
    old_key, new_k = new_key(), new_key()
    old_cipher = AesGcmCipher(keys={"k1": old_key}, active_key_id="k1", index_key=index_key)
    old_blob = old_cipher.encrypt("Rajesh Kumar")

    rotated = AesGcmCipher(
        keys={"k1": old_key, "k2": new_k}, active_key_id="k2", index_key=index_key
    )
    assert rotated.decrypt(old_blob) == "Rajesh Kumar"
    new_blob = rotated.encrypt("Rajesh Kumar")
    assert rotated.key_id_of(new_blob) == "k2"
    assert rotated.decrypt(new_blob) == "Rajesh Kumar"
    # The retired reader cannot open values written under the new key.
    with pytest.raises(DecryptionError):
        old_cipher.decrypt(new_blob)


def test_blind_index_depends_on_the_index_key_only(keys: dict[str, bytes]) -> None:
    """TT-AC17-P3: different index key -> different index; encryption key is irrelevant."""
    first = AesGcmCipher(keys=keys, active_key_id="k1", index_key=new_key())
    second = AesGcmCipher(keys=keys, active_key_id="k1", index_key=new_key())
    assert first.blind_index("A1") != second.blind_index("A1")
    shared_index = new_key()
    a = AesGcmCipher(keys={"k1": new_key()}, active_key_id="k1", index_key=shared_index)
    b = AesGcmCipher(keys={"k1": new_key()}, active_key_id="k1", index_key=shared_index)
    assert a.blind_index("A1") == b.blind_index("A1")


def test_ciphertext_for_devanagari_is_not_valid_plaintext_either_way(
    cipher: AesGcmCipher,
) -> None:
    """TT-AC17-P1: UTF-8 encoding is used consistently for non-ASCII text."""
    blob = cipher.encrypt(DEV_NAME)
    assert DEV_NAME.encode("utf-16") not in blob
    assert cipher.decrypt(blob) == DEV_NAME
