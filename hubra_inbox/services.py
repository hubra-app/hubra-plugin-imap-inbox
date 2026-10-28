"""Mailboxes, who may read them, and syncing them over IMAP."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select

from hubra.api.permissions import (
    _derive_perm_key,
    _get_member_permission_keys,
    member_is_admin,
)
from hubra.core.errors import raise_error
from hubra.core.extensions import db
from hubra.core.models.group import Group, GroupMembership

from . import crypto, imap, parse
from .models import SECURITY, InboxMailbox, InboxMessage

_log = logging.getLogger(__name__)

# One sync run fetches at most this many new messages per folder; the rest
# follow on the next run.
BATCH = 200


# ── Access ───────────────────────────────────────────────────────────────────


def can_manage(member) -> bool:
    if member_is_admin(member):
        return True
    key = _derive_perm_key("inbox_bp", "mailboxes", "manage")
    return key in _get_member_permission_keys(member)


def visible_mailbox_ids(member) -> set[int]:
    q = select(InboxMailbox.id)
    if not can_manage(member):
        groups = select(GroupMembership.group_id).where(
            GroupMembership.member_id == member.id
        )
        q = q.where(InboxMailbox.group_id.in_(groups))
    return set(db.session.scalars(q))


def mailbox_for(member, mailbox_id: int) -> InboxMailbox:
    mailbox = db.session.get(InboxMailbox, mailbox_id)
    if mailbox is None or mailbox.id not in visible_mailbox_ids(member):
        raise_error(404, "NOT_FOUND", "Mailbox not found")
    return mailbox


def message_for(member, message_id: int) -> InboxMessage:
    message = db.session.get(InboxMessage, message_id)
    if message is None or message.mailbox_id not in visible_mailbox_ids(member):
        raise_error(404, "NOT_FOUND", "Message not found")
    return message


# ── Serialisation ────────────────────────────────────────────────────────────


def mailbox_to_dict(m: InboxMailbox, manage: bool) -> dict:
    out = {
        "id": m.id,
        "name": m.name,
        "groupId": m.group_id,
        "groupName": m.group.name if m.group else None,
        "active": m.active,
        "lastSyncAt": m.last_sync_at.isoformat() if m.last_sync_at else None,
        "lastError": m.last_error,
        "unread": db.session.scalar(
            select(func.count())
            .select_from(InboxMessage)
            .where(InboxMessage.mailbox_id == m.id, InboxMessage.done.is_(False))
        ),
    }
    if manage:
        out.update(
            {
                "host": m.host,
                "port": m.port,
                "security": m.security,
                "username": m.username,
                "hasPassword": bool(m.password_encrypted),
                "folders": list(m.folders or []),
                "markSeen": m.mark_seen,
                "retentionDays": m.retention_days,
            }
        )
    return out


def message_to_dict(m: InboxMessage, full: bool = False) -> dict:
    out = {
        "id": m.id,
        "mailboxId": m.mailbox_id,
        "folder": m.folder,
        "subject": m.subject,
        "fromName": m.from_name,
        "fromAddress": m.from_address,
        "sentAt": m.sent_at.isoformat() if m.sent_at else None,
        "threadKey": m.thread_key,
        "hasAttachments": bool(m.attachments),
        "done": m.done,
        "preview": (m.text_body or "")[:160].replace("\n", " ").strip(),
    }
    if full:
        out.update(
            {
                "to": m.to_addresses,
                "cc": m.cc_addresses,
                "text": m.text_body,
                "html": m.html_body,
                "attachments": list(m.attachments or []),
                "truncated": m.truncated,
                "size": m.size,
            }
        )
    return out


# ── Mailboxes ────────────────────────────────────────────────────────────────


def _validate(data: dict, partial: bool) -> dict:
    out: dict = {}
    for key, attr, limit in (
        ("name", "name", 120),
        ("host", "host", 255),
        ("username", "username", 255),
    ):
        if key in data:
            value = str(data.get(key) or "").strip()
            if not value:
                raise_error(400, "VALIDATION_ERROR", f"{key} is required")
            out[attr] = value[:limit]
    if "port" in data:
        try:
            port = int(data["port"])
        except (TypeError, ValueError):
            raise_error(400, "VALIDATION_ERROR", "port must be a number")
        if not 1 <= port <= 65535:
            raise_error(400, "VALIDATION_ERROR", "port must be between 1 and 65535")
        out["port"] = port
    if "security" in data:
        if data["security"] not in SECURITY:
            raise_error(400, "VALIDATION_ERROR", "security is ssl or starttls")
        out["security"] = data["security"]
    if data.get("password"):
        out["password_encrypted"] = crypto.encrypt(str(data["password"]))
    if "folders" in data:
        folders = data["folders"]
        if not isinstance(folders, list) or not all(
            isinstance(f, str) for f in folders
        ):
            raise_error(400, "VALIDATION_ERROR", "folders must be a list of names")
        folders = [f.strip()[:255] for f in folders if f.strip()][:20]
        out["folders"] = folders or ["INBOX"]
    if "groupId" in data:
        group_id = data["groupId"]
        if group_id is not None and db.session.get(Group, group_id) is None:
            raise_error(404, "NOT_FOUND", "Group not found")
        out["group_id"] = group_id
    for key, attr in (("markSeen", "mark_seen"), ("active", "active")):
        if key in data:
            out[attr] = bool(data[key])
    if "retentionDays" in data:
        try:
            days = int(data["retentionDays"])
        except (TypeError, ValueError):
            raise_error(400, "VALIDATION_ERROR", "retentionDays must be a number")
        out["retention_days"] = max(1, min(days, 3650))
    if not partial:
        for required in ("name", "host", "username", "password_encrypted"):
            if required not in out:
                field = "password" if required == "password_encrypted" else required
                raise_error(400, "VALIDATION_ERROR", f"{field} is required")
    if "host" in out or "port" in out:
        host = out.get("host")
        port = out.get("port", 993)
        if host:
            try:
                imap.resolve(host, port)
            except imap.ImapError as exc:
                raise_error(400, "VALIDATION_ERROR", str(exc))
    return out


class MailboxService:
    @staticmethod
    def list_for(member) -> list[InboxMailbox]:
        ids = visible_mailbox_ids(member)
        if not ids:
            return []
        return list(
            db.session.scalars(
                select(InboxMailbox)
                .where(InboxMailbox.id.in_(ids))
                .order_by(InboxMailbox.name)
            )
        )

    @staticmethod
    def create(data: dict) -> InboxMailbox:
        values = _validate(data, partial=False)
        values.setdefault("folders", ["INBOX"])
        mailbox = InboxMailbox(**values)
        db.session.add(mailbox)
        db.session.flush()
        return mailbox

    @staticmethod
    def update(mailbox: InboxMailbox, data: dict) -> InboxMailbox:
        values = _validate(data, partial=True)
        server_changed = any(
            k in values and values[k] != getattr(mailbox, k)
            for k in ("host", "port", "username", "security")
        )
        if server_changed and "password_encrypted" not in values:
            # The stored password must never be sent to another server.
            raise_error(
                400,
                "PASSWORD_REQUIRED",
                "Enter the password again when you change the server or user name",
            )
        for key, value in values.items():
            setattr(mailbox, key, value)
        if server_changed:
            # Another account: its UIDs mean something else.
            mailbox.sync_state = {}
        mailbox.last_error = None
        db.session.flush()
        return mailbox

    @staticmethod
    def delete(mailbox: InboxMailbox) -> None:
        db.session.execute(
            delete(InboxMessage).where(InboxMessage.mailbox_id == mailbox.id)
        )
        db.session.delete(mailbox)
        db.session.flush()


def account_of(mailbox: InboxMailbox) -> imap.Account:
    return imap.Account(
        host=mailbox.host,
        port=mailbox.port,
        security=mailbox.security,
        username=mailbox.username,
        password=crypto.decrypt(mailbox.password_encrypted),
    )


def test_account(account: imap.Account) -> list[str]:
    """Log in and list the folders.  Raises ImapError."""
    conn = imap.connect(account)
    try:
        return imap.list_folders(conn)
    finally:
        imap.close(conn)


# ── Sync ─────────────────────────────────────────────────────────────────────


def _store(
    mailbox: InboxMailbox, folder: str, validity: int, uid: int, raw, size
) -> None:
    truncated = size > imap.MAX_MESSAGE_BYTES
    try:
        p = parse.parse(raw or b"")
    except Exception:  # noqa: BLE001 - one broken message must not stop the sync
        _log.warning("inbox %s: message %s can't be parsed", mailbox.id, uid)
        p = parse.parse(b"Subject: (unreadable message)\r\n\r\n")
    db.session.add(
        InboxMessage(
            mailbox_id=mailbox.id,
            folder=folder,
            uid=uid,
            uidvalidity=validity,
            message_id=p.message_id,
            thread_key=p.thread_key,
            subject=p.subject,
            from_name=p.from_name,
            from_address=p.from_address,
            to_addresses=p.to_addresses,
            cc_addresses=p.cc_addresses,
            sent_at=p.sent_at,
            text_body=p.text_body,
            html_body=p.html_body,
            attachments=p.attachments,
            size=size or len(raw or b""),
            truncated=truncated,
        )
    )


def sync_mailbox(mailbox: InboxMailbox) -> dict:
    """Fetch new messages of every folder.  Errors are stored, not raised."""
    now = datetime.now(timezone.utc)
    fetched = 0
    try:
        account = account_of(mailbox)
        # Re-encrypt with the current key (after a key rotation).
        mailbox.password_encrypted = crypto.rotate(mailbox.password_encrypted)
        conn = imap.connect(account)
    except (imap.ImapError, ValueError) as exc:
        mailbox.last_error = str(exc)[:500]
        mailbox.last_sync_at = now
        return {"error": mailbox.last_error}
    state = dict(mailbox.sync_state or {})
    since = (now - timedelta(days=mailbox.retention_days)).strftime("%d-%b-%Y")
    try:
        for folder in mailbox.folders or ["INBOX"]:
            validity = imap.select(conn, folder, readonly=not mailbox.mark_seen)
            # A copy: changing the stored dict in place would not be saved.
            folder_state = dict(state.get(folder) or {})
            if folder_state.get("uidvalidity") != validity:
                # New folder, or the server renumbered it: start again.
                db.session.execute(
                    delete(InboxMessage).where(
                        InboxMessage.mailbox_id == mailbox.id,
                        InboxMessage.folder == folder,
                    )
                )
                folder_state = {"uidvalidity": validity, "last_uid": 0}
            uids = imap.uids_after(conn, folder_state["last_uid"], since)[:BATCH]
            for uid in uids:
                raw, size = imap.fetch(conn, uid, peek=not mailbox.mark_seen)
                _store(mailbox, folder, validity, uid, raw, size)
                folder_state["last_uid"] = uid
                fetched += 1
            state[folder] = folder_state
        mailbox.last_error = None
    except imap.ImapError as exc:
        mailbox.last_error = str(exc)[:500]
    finally:
        imap.close(conn)
    mailbox.sync_state = state
    mailbox.last_sync_at = now
    cutoff = now - timedelta(days=mailbox.retention_days)
    db.session.execute(
        delete(InboxMessage).where(
            InboxMessage.mailbox_id == mailbox.id,
            or_(InboxMessage.sent_at < cutoff, InboxMessage.fetched_at < cutoff),
        )
    )
    db.session.flush()
    return {"fetched": fetched, "error": mailbox.last_error}


def sync_all() -> dict:
    results = {}
    for mailbox in db.session.scalars(
        select(InboxMailbox).where(InboxMailbox.active.is_(True))
    ):
        results[mailbox.id] = sync_mailbox(mailbox)
        db.session.commit()
    return results


# ── Messages ─────────────────────────────────────────────────────────────────


class MessageService:
    @staticmethod
    def list_for(
        member,
        mailbox_id: int | None,
        query: str | None,
        done: bool | None,
        before_id: int | None,
        limit: int = 50,
    ) -> list[InboxMessage]:
        ids = visible_mailbox_ids(member)
        if mailbox_id is not None:
            ids &= {mailbox_id}
        if not ids:
            return []
        q = select(InboxMessage).where(InboxMessage.mailbox_id.in_(ids))
        if done is not None:
            q = q.where(InboxMessage.done.is_(done))
        if query:
            like = f"%{query.strip()[:100]}%"
            q = q.where(
                or_(
                    InboxMessage.subject.ilike(like),
                    InboxMessage.from_name.ilike(like),
                    InboxMessage.from_address.ilike(like),
                    InboxMessage.text_body.ilike(like),
                )
            )
        if before_id:
            q = q.where(InboxMessage.id < before_id)
        q = q.order_by(InboxMessage.sent_at.desc().nullslast(), InboxMessage.id.desc())
        return list(db.session.scalars(q.limit(max(1, min(limit, 100)))))

    @staticmethod
    def thread(message: InboxMessage) -> list[InboxMessage]:
        if not message.thread_key:
            return [message]
        return list(
            db.session.scalars(
                select(InboxMessage)
                .where(
                    InboxMessage.mailbox_id == message.mailbox_id,
                    InboxMessage.thread_key == message.thread_key,
                )
                .order_by(InboxMessage.sent_at.asc().nullsfirst(), InboxMessage.id)
            )
        )

    @staticmethod
    def attachment(message: InboxMessage, index: int) -> tuple[str, str, bytes]:
        """Fetch one attachment from the server (bodies aren't stored)."""
        if not any(a.get("index") == index for a in message.attachments or []):
            raise_error(404, "NOT_FOUND", "Attachment not found")
        mailbox = message.mailbox
        try:
            conn = imap.connect(account_of(mailbox))
        except (imap.ImapError, ValueError) as exc:
            raise_error(502, "MAILBOX_UNREACHABLE", str(exc))
        try:
            validity = imap.select(conn, message.folder, readonly=True)
            if validity != message.uidvalidity:
                raise_error(410, "GONE", "The message is no longer on the server")
            raw, _ = imap.fetch(conn, message.uid, peek=True)
        except imap.ImapError as exc:
            raise_error(502, "MAILBOX_UNREACHABLE", str(exc))
        finally:
            imap.close(conn)
        found = parse.attachment(raw or b"", index)
        if found is None:
            raise_error(404, "NOT_FOUND", "Attachment not found")
        return found
