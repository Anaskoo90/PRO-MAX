"""
Encryption Services: symmetric field-level encryption for sensitive
columns (e.g. stored OAuth tokens for third-party integrations). Uses
Fernet (AES-128-CBC + HMAC, via the `cryptography` package) — authenticated
encryption, so tampering is detected on decrypt, not just confidentiality.
Key management/rotation is delegated to SecretProvider (secrets_provider.py);
this class only performs the encrypt/decrypt operation.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class FieldEncryptionError(Exception):
    pass


class FieldEncryptionService:
    def __init__(self, encryption_key: bytes) -> None:
        self._fernet = Fernet(encryption_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise FieldEncryptionError("Ciphertext is invalid or was tampered with") from exc

    @staticmethod
    def generate_key() -> bytes:
        return Fernet.generate_key()
