"""Envelope encryption for secrets at rest (spec §10 Security: AES-256-GCM,
envelope encryption, key id for rotation).

Used first by the ``youtube`` module to encrypt OAuth access/refresh tokens
before they are persisted (spec §3 YouTube connection: "Tokens encrypted at
rest ... never logged, revoked on disconnect"). A single master key, read
from ``TOKEN_ENCRYPTION_KEY``, is identified by ``key_id`` so a future key
rotation can decrypt old ciphertext by the key id stored alongside it while
encrypting new values under the newest key - the rotation mechanism itself
(a key registry keyed by id) is deferred until there is a second key to
rotate to; adding one is additive, not a breaking change to this module's
public shape (``EncryptedValue``).
"""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12  # 96-bit nonce, the size AES-GCM is designed for.
_KEY_BYTES = 32  # AES-256.


class CryptoError(Exception):
    """A key is malformed, or a ciphertext failed to authenticate."""


@dataclass(frozen=True, slots=True)
class EncryptedValue:
    """A ciphertext plus the nonce and key id needed to decrypt it.

    ``key_id`` is stored so a future key rotation can tell which key
    encrypted this value, even after the master key has been rotated.
    """

    key_id: str
    nonce: bytes
    ciphertext: bytes

    def to_storable(self) -> str:
        """Pack into one opaque string for a single encrypted-text database column."""
        return f"{self.key_id}:{base64.b64encode(self.nonce).decode()}:{base64.b64encode(self.ciphertext).decode()}"

    @classmethod
    def from_storable(cls, raw: str) -> EncryptedValue:
        try:
            key_id, nonce_b64, ciphertext_b64 = raw.split(":", 2)
            return cls(
                key_id=key_id,
                nonce=base64.b64decode(nonce_b64, validate=True),
                ciphertext=base64.b64decode(ciphertext_b64, validate=True),
            )
        except (ValueError, binascii.Error) as exc:
            raise CryptoError(f"malformed encrypted value: {exc}") from exc


def load_key(encoded: str) -> bytes:
    """Decode a base64-encoded 32-byte (256-bit) key from settings."""
    try:
        key = base64.b64decode(encoded)
    except (ValueError, TypeError) as exc:
        raise CryptoError("TOKEN_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != _KEY_BYTES:
        raise CryptoError(f"TOKEN_ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes, got {len(key)}")
    return key


def generate_key() -> str:
    """A fresh base64-encoded 256-bit key, for seeding ``.env``/``.env.example``."""
    return base64.b64encode(os.urandom(_KEY_BYTES)).decode()


class TokenCipher:
    """Encrypts and decrypts short secrets (OAuth tokens) with one named key."""

    def __init__(self, key_id: str, key: bytes) -> None:
        if len(key) != _KEY_BYTES:
            raise CryptoError(f"key must be {_KEY_BYTES} bytes, got {len(key)}")
        self._key_id = key_id
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> EncryptedValue:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return EncryptedValue(key_id=self._key_id, nonce=nonce, ciphertext=ciphertext)

    def decrypt(self, value: EncryptedValue) -> str:
        if value.key_id != self._key_id:
            raise CryptoError(
                f"ciphertext was encrypted under key {value.key_id!r}, "
                f"this cipher only holds {self._key_id!r}"
            )
        try:
            plaintext = self._aesgcm.decrypt(value.nonce, value.ciphertext, None)
        except InvalidTag as exc:
            raise CryptoError("ciphertext failed to authenticate (wrong key or tampered)") from exc
        return plaintext.decode("utf-8")
