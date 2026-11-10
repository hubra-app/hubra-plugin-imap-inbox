"""Dashboard widget of the shared inbox (docs/dashboards.md in hubra-app/hubra).

inbox.open  list  mails not marked done yet, newest first, from the mailboxes
                  the viewer may read

It reads as the viewing member, who needs ``inbox.messages.read``.
"""

from __future__ import annotations

from sqlalchemy import func, select

from hubra.core.extensions import db

from .models import InboxMessage
from .services import visible_mailbox_ids


def open_mails(ctx, config: dict) -> dict:
    try:
        count = max(1, min(int(config.get("count") or 5), 20))
    except (TypeError, ValueError):
        count = 5
    ids = visible_mailbox_ids(ctx.actor) if ctx.actor is not None else set()
    if not ids:
        return {"items": [], "total": 0}
    base = (
        select(InboxMessage)
        .where(InboxMessage.mailbox_id.in_(ids))
        .where(InboxMessage.done.is_(False))
    )
    total = db.session.scalar(select(func.count()).select_from(base.subquery()))
    rows = db.session.scalars(
        base.order_by(InboxMessage.sent_at.desc().nullslast(), InboxMessage.id.desc()).limit(
            count
        )
    )
    items = []
    for m in rows:
        sender = m.from_name or m.from_address
        when = f"{m.sent_at:%d.%m. %H:%M}" if m.sent_at else None
        items.append(
            {
                "label": m.subject or "–",
                "sub": " · ".join(p for p in (sender, when) if p) or None,
                "path": "/app/inbox",
            }
        )
    return {"items": items, "total": total or 0}
