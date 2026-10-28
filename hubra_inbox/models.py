"""Shared inbox tables (tenant schema).

InboxMailbox: one IMAP account of the club, its password encrypted.
InboxMessage: one message read from it, with a sanitised body.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hubra.core.extensions import db

SECURITY = ("ssl", "starttls")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InboxMailbox(db.Model):
    __tablename__ = "inbox_mailboxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    host: Mapped[str] = mapped_column(db.String(255), nullable=False)
    port: Mapped[int] = mapped_column(db.Integer, nullable=False, default=993)
    # ssl: TLS from the start (993); starttls: plain, then STARTTLS (143).
    security: Mapped[str] = mapped_column(db.String(10), nullable=False, default="ssl")
    username: Mapped[str] = mapped_column(db.String(255), nullable=False)
    # Fernet token (crypto.py); never sent to the browser.
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    folders: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: ["INBOX"]
    )
    # Members of this group read the mailbox; None: only inbox managers.
    group_id: Mapped[int | None] = mapped_column(
        db.Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True
    )
    # Off (default): Hubra opens folders read-only and never changes a flag.
    mark_seen: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, default=False, server_default=false()
    )
    active: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, default=True, server_default=true()
    )
    retention_days: Mapped[int] = mapped_column(db.Integer, nullable=False, default=180)
    # folder -> {"uidvalidity": int, "last_uid": int}
    sync_state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(db.String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    group = relationship("Group")


class InboxMessage(db.Model):
    __tablename__ = "inbox_messages"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_id", "folder", "uidvalidity", "uid", name="uq_inbox_message_uid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    mailbox_id: Mapped[int] = mapped_column(
        db.Integer,
        ForeignKey("inbox_mailboxes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    folder: Mapped[str] = mapped_column(db.String(255), nullable=False)
    uid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uidvalidity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    # The Message-ID of the conversation's first message, for threading.
    thread_key: Mapped[str | None] = mapped_column(
        db.String(255), nullable=True, index=True
    )
    subject: Mapped[str | None] = mapped_column(db.String(500), nullable=True)
    from_name: Mapped[str | None] = mapped_column(db.String(255), nullable=True)
    from_address: Mapped[str | None] = mapped_column(db.String(320), nullable=True)
    to_addresses: Mapped[str | None] = mapped_column(Text, nullable=True)
    cc_addresses: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    text_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sanitised with nh3: no scripts, styles, forms or event handlers.
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"index": n, "filename": ..., "contentType": ..., "size": bytes}]
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    size: Mapped[int] = mapped_column(db.Integer, nullable=False, default=0)
    # Larger than the limit: only the headers were stored.
    truncated: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, default=False, server_default=false()
    )
    done: Mapped[bool] = mapped_column(
        db.Boolean, nullable=False, default=False, server_default=false()
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    mailbox = relationship("InboxMailbox")
