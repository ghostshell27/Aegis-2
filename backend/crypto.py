"""Local secret encryption for the stored API key.

We derive an AES-256 key from the machine's hostname using PBKDF2 and
encrypt with AES-GCM. This is intentionally machine-bound: the ciphertext
on the USB drive is only readable on the host that wrote it, which is
what we want for a classroom/portable setup. It is NOT a substitute for
proper key management -- an attacker with shell access to the same
machine can re-derive the key.
"""
from __future__ import annotations

import os
import socket
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_SALT = b"mathcore-fixed-salt-v1"
_ITERATIONS = 200_000
_NONCE_BYTES = 12


def _machine_secret() -> bytes:
    host = socket.gethostname() or "mathcore"
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "local"
    seed = f"{host}|{username}".encode("utf-8")
    return seed


def derive_key() -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=_ITERATIONS,
    )
    return kdf.derive(_machine_secret())


def encrypt(plaintext: str) -> bytes:
    if plaintext is None:
        plaintext = ""
    key = derive_key()
    aes = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=b"mathcore")
    return nonce + ct


def decrypt(blob: bytes) -> str:
    if not blob:
        return ""
    key = derive_key()
    aes = AESGCM(key)
    nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    try:
        pt = aes.decrypt(nonce, ct, associated_data=b"mathcore")
        return pt.decode("utf-8")
    except Exception:
        # If the user copied the USB to a different host the key no longer
        # matches -- return empty so the UI can re-prompt for setup.
        return ""
