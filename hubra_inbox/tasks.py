"""Celery tasks: sync every active mailbox, every five minutes."""

from __future__ import annotations

from hubra.core.extensions import db
from hubra.core.modules import per_tenant_job
from hubra.core.tasks import celery_app

from . import services
from .models import InboxMailbox


@celery_app.task(name="hubra_inbox.tasks.sync_all")
@per_tenant_job("inbox")
def sync_all() -> dict:
    return services.sync_all()


@celery_app.task(name="hubra_inbox.tasks.sync_one")
@per_tenant_job("inbox")
def sync_one(mailbox_id: int) -> dict:
    mailbox = db.session.get(InboxMailbox, mailbox_id)
    if mailbox is None:
        return {"error": "gone"}
    result = services.sync_mailbox(mailbox)
    db.session.commit()
    return result
