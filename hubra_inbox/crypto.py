"""Encryption of mailbox passwords.

The key is derived from ``FERNET_KEY`` (or ``SECRET_KEY``) for this plugin
only, so a door code key and a mailbox key are never the same.  Keys
listed in ``FERNET_OLD_KEYS`` (comma-separated) still decrypt, so the main
key can be rotated: set the new one and keep the old one there until every
mailbox has synced once (each sync re-encrypts with the current key).
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from flask import current_app

_CONTEXT = b"hubra-plugin:imap-inbox:v1"


def _derive(secret: str) -> Fernet:
    digest = hashlib.sha256(_CONTEXT + b"|" + secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _fernet() -> MultiFernet:
    cfg = current_app.config
    main = cfg.get("FERNET_KEY") or cfg["SECRET_KEY"]
    raw = cfg.get("FERNET_OLD_KEYS") or os.environ.get("FERNET_OLD_KEYS") or ""
    old = [k.strip() for k in str(raw).split(",")]
    return MultiFernet([_derive(main), *(_derive(k) for k in old if k)])


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("The stored password can't be decrypted") from exc


def rotate(ciphertext: str) -> str:
    return _fernet().rotate(ciphertext.encode("ascii")).decode("ascii")
