"""IMAP connections.

- The host name is resolved once and checked: private, loopback and
  link-local addresses are refused (``INBOX_ALLOW_PRIVATE_HOSTS`` lifts that
  for a mail server in the same network).  The connection then goes to that
  checked address, so a DNS answer can't change between check and connect.
- TLS certificates are always verified, against the host name.
- Folders are opened read-only (``EXAMINE``) and bodies fetched with
  ``BODY.PEEK``, so reading never changes the mailbox, unless a mailbox has
  ``mark_seen`` on.
"""

from __future__ import annotations

import imaplib
import ipaddress
import os
import re
import socket
import ssl
from dataclasses import dataclass

from flask import current_app

TIMEOUT = 20
# Messages above this size are stored with their headers only.
MAX_MESSAGE_BYTES = 25 * 1024 * 1024


class ImapError(Exception):
    """Shown to the user; never contains the password."""


def _allow_private() -> bool:
    raw = current_app.config.get("INBOX_ALLOW_PRIVATE_HOSTS")
    if raw is None:
        raw = os.environ.get("INBOX_ALLOW_PRIVATE_HOSTS", "")
    return str(raw).lower() in ("1", "true", "yes")


def resolve(host: str, port: int) -> str:
    """The address to connect to, after the private-network check."""
    host = (host or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}|\[?[0-9a-fA-F:]+\]?", host):
        raise ImapError("The server name isn't valid")
    if not 1 <= int(port) <= 65535:
        raise ImapError("The port isn't valid")
    try:
        infos = socket.getaddrinfo(host.strip("[]"), port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ImapError(f"The server {host} can't be found") from exc
    for info in infos:
        address = info[4][0]
        ip = ipaddress.ip_address(address)
        if not ip.is_global and not _allow_private():
            continue
        return address
    raise ImapError(f"The server {host} is in a private network, which is not allowed")


class _PinnedSSL(imaplib.IMAP4_SSL):
    def __init__(self, host, port, address, context):
        self._address = address
        super().__init__(host, port, ssl_context=context, timeout=TIMEOUT)

    def _create_socket(self, timeout):
        sock = socket.create_connection((self._address, self.port), timeout)
        return self.ssl_context.wrap_socket(sock, server_hostname=self.host)


class _PinnedPlain(imaplib.IMAP4):
    def __init__(self, host, port, address):
        self._address = address
        super().__init__(host, port, timeout=TIMEOUT)

    def _create_socket(self, timeout):
        return socket.create_connection((self._address, self.port), timeout)


@dataclass
class Account:
    host: str
    port: int
    security: str
    username: str
    password: str


def connect(account: Account) -> imaplib.IMAP4:
    """A logged-in connection.  Raises ImapError."""
    address = resolve(account.host, account.port)
    context = ssl.create_default_context()
    try:
        if account.security == "ssl":
            conn: imaplib.IMAP4 = _PinnedSSL(
                account.host, account.port, address, context
            )
        else:
            conn = _PinnedPlain(account.host, account.port, address)
            conn.starttls(ssl_context=context)
        conn.login(account.username, account.password)
    except ssl.SSLError as exc:
        raise ImapError(f"Secure connection failed: {exc.reason or exc}") from exc
    except imaplib.IMAP4.error as exc:
        text = (
            str(exc).replace(account.password, "***") if account.password else str(exc)
        )
        raise ImapError(f"Login failed: {text[:200]}") from exc
    except OSError as exc:
        raise ImapError(f"Can't reach {account.host}:{account.port}: {exc}") from exc
    return conn


def close(conn: imaplib.IMAP4) -> None:
    try:
        conn.logout()
    except Exception:  # noqa: BLE001 - closing is best effort
        pass


_LIST_RE = re.compile(rb'\((?P<flags>[^)]*)\) (?P<sep>"[^"]*"|NIL) (?P<name>.+)$')


def list_folders(conn: imaplib.IMAP4) -> list[str]:
    status, data = conn.list()
    if status != "OK":
        return []
    folders = []
    for raw in data:
        if not isinstance(raw, bytes):
            continue
        m = _LIST_RE.match(raw)
        if not m or b"\\Noselect" in m["flags"]:
            continue
        name = m["name"].strip()
        if name.startswith(b'"') and name.endswith(b'"'):
            name = name[1:-1].replace(b'\\"', b'"')
        folders.append(name.decode("utf-8", "replace"))
    return folders


def _quote(folder: str) -> str:
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def select(conn: imaplib.IMAP4, folder: str, readonly: bool = True) -> int:
    """Open *folder*; returns its UIDVALIDITY."""
    status, data = conn.select(_quote(folder), readonly=readonly)
    if status != "OK":
        raise ImapError(f"Folder {folder} can't be opened")
    _, validity = conn.response("UIDVALIDITY")
    try:
        return int(validity[0])
    except (TypeError, ValueError, IndexError):
        return 0


def uids_after(
    conn: imaplib.IMAP4, last_uid: int, since: str | None = None
) -> list[int]:
    """UIDs above *last_uid*; on a first sync those since *since* (DD-Mon-YYYY)."""
    if last_uid:
        status, data = conn.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    elif since:
        status, data = conn.uid("SEARCH", None, f"SINCE {since}")
    else:
        status, data = conn.uid("SEARCH", None, "ALL")
    if status != "OK" or not data or not data[0]:
        return []
    # "UID n:*" always returns the last message, even below n.
    return sorted(u for u in (int(x) for x in data[0].split()) if u > last_uid)


def fetch(conn: imaplib.IMAP4, uid: int, peek: bool = True) -> tuple[bytes | None, int]:
    """(raw message, size in bytes).  Above the size limit: the headers only."""
    status, data = conn.uid("FETCH", str(uid), "(RFC822.SIZE)")
    size = 0
    if status == "OK" and data and isinstance(data[0], bytes):
        m = re.search(rb"RFC822\.SIZE (\d+)", data[0])
        size = int(m.group(1)) if m else 0
    part = "BODY.PEEK[]" if peek else "BODY[]"
    if size > MAX_MESSAGE_BYTES:
        part = "BODY.PEEK[HEADER]" if peek else "BODY[HEADER]"
    status, data = conn.uid("FETCH", str(uid), f"({part})")
    if status != "OK":
        raise ImapError(f"Message {uid} can't be read")
    raw = next((d[1] for d in data if isinstance(d, tuple) and len(d) > 1), None)
    return raw, size
