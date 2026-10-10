"""Tests for AES-256-GCM envelope encryption (spec §10, Phase 1A)."""

from __future__ import annotations

import pytest

from creatoriqx_api.platform.crypto import (
    CryptoError,
    EncryptedValue,
    TokenCipher,
    generate_key,
    load_key,
)


class TestLoadKey:
    def test_generated_key_round_trips(self) -> None:
        encoded = generate_key()
        key = load_key(encoded)
        assert len(key) == 32

    def test_rejects_invalid_base64(self) -> None:
        with pytest.raises(CryptoError, match="not valid base64"):
            load_key("not-valid-base64!!!")

    def test_rejects_wrong_length(self) -> None:
        import base64

        short_key = base64.b64encode(b"too-short").decode()
        with pytest.raises(CryptoError, match="must decode to 32 bytes"):
            load_key(short_key)


class TestTokenCipher:
    @pytest.fixture
    def cipher(self) -> TokenCipher:
        return TokenCipher("k1", load_key(generate_key()))

    def test_encrypt_then_decrypt_round_trips(self, cipher: TokenCipher) -> None:
        plaintext = "ya29.a0AfH6SMB_super_secret_access_token"
        value = cipher.encrypt(plaintext)
        assert cipher.decrypt(value) == plaintext

    def test_ciphertext_is_not_the_plaintext(self, cipher: TokenCipher) -> None:
        value = cipher.encrypt("super-secret")
        assert b"super-secret" not in value.ciphertext

    def test_storable_round_trips_through_a_string(self, cipher: TokenCipher) -> None:
        value = cipher.encrypt("a-refresh-token")
        raw = value.to_storable()
        restored = EncryptedValue.from_storable(raw)
        assert cipher.decrypt(restored) == "a-refresh-token"

    def test_storable_carries_the_key_id(self, cipher: TokenCipher) -> None:
        value = cipher.encrypt("x")
        assert value.to_storable().startswith("k1:")

    def test_tampered_ciphertext_fails_to_decrypt(self, cipher: TokenCipher) -> None:
        value = cipher.encrypt("a-token")
        tampered = EncryptedValue(
            key_id=value.key_id, nonce=value.nonce, ciphertext=value.ciphertext[:-1] + b"\x00"
        )
        with pytest.raises(CryptoError, match="failed to authenticate"):
            cipher.decrypt(tampered)

    def test_decrypting_with_the_wrong_key_id_is_refused(self, cipher: TokenCipher) -> None:
        value = cipher.encrypt("a-token")
        other_cipher = TokenCipher("k2", load_key(generate_key()))
        with pytest.raises(CryptoError, match="only holds 'k2'"):
            other_cipher.decrypt(value)

    def test_malformed_storable_string_is_refused(self) -> None:
        with pytest.raises(CryptoError, match="malformed encrypted value"):
            EncryptedValue.from_storable("not-the-right-shape")

    def test_construction_rejects_wrong_key_length(self) -> None:
        with pytest.raises(CryptoError, match="key must be 32 bytes"):
            TokenCipher("k1", b"too-short")
