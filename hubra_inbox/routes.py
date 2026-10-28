"""Shared inbox blueprint: /api/v1/inbox."""

from __future__ import annotations

import io

from flask import Blueprint, jsonify, request, send_file

from hubra.api.auth.helpers import get_current_member
from hubra.api.permissions import permission_required
from hubra.api.utils import log_audit
from hubra.core.errors import api_error
from hubra.core.extensions import db

from . import imap, services
from .models import SECURITY
from .services import (
    MailboxService,
    MessageService,
    can_manage,
    mailbox_for,
    mailbox_to_dict,
    message_for,
    message_to_dict,
)

inbox_bp = Blueprint("inbox_bp", __name__)


def _body() -> dict:
    return request.get_json(silent=True) or {}


# ── Mailboxes ────────────────────────────────────────────────────────────────


@inbox_bp.get("/mailboxes")
@permission_required("messages", "read", "Read the shared inbox")
def list_mailboxes():
    member = get_current_member()
    manage = can_manage(member)
    mailboxes = MailboxService.list_for(member)
    return jsonify(
        {
            "canManage": manage,
            "mailboxes": [mailbox_to_dict(m, manage) for m in mailboxes],
        }
    ), 200


@inbox_bp.post("/mailboxes")
@permission_required("mailboxes", "manage", "Set up shared mailboxes")
def create_mailbox():
    mailbox = MailboxService.create(_body())
    log_audit(
        get_current_member().id,
        "create_inbox_mailbox",
        "InboxMailbox",
        mailbox.id,
        mailbox.name,
    )
    db.session.commit()
    return jsonify(mailbox_to_dict(mailbox, True)), 201


@inbox_bp.patch("/mailboxes/<int:mailbox_id>")
@permission_required("mailboxes", "manage", "Set up shared mailboxes")
def update_mailbox(mailbox_id: int):
    member = get_current_member()
    mailbox = mailbox_for(member, mailbox_id)
    body = _body()
    MailboxService.update(mailbox, body)
    changed = ", ".join(sorted(k if k != "password" else "password" for k in body))
    log_audit(
        member.id,
        "update_inbox_mailbox",
        "InboxMailbox",
        mailbox.id,
        f"{mailbox.name}: {changed}",
    )
    db.session.commit()
    return jsonify(mailbox_to_dict(mailbox, True)), 200


@inbox_bp.delete("/mailboxes/<int:mailbox_id>")
@permission_required("mailboxes", "manage", "Set up shared mailboxes")
def delete_mailbox(mailbox_id: int):
    member = get_current_member()
    mailbox = mailbox_for(member, mailbox_id)
    log_audit(
        member.id, "delete_inbox_mailbox", "InboxMailbox", mailbox.id, mailbox.name
    )
    MailboxService.delete(mailbox)
    db.session.commit()
    return "", 204


@inbox_bp.post("/mailboxes/test")
@permission_required("mailboxes", "manage", "Set up shared mailboxes")
def test_mailbox():
    """Log in with the given settings (or a saved mailbox's) and list folders."""
    body = _body()
    member = get_current_member()
    try:
        if body.get("mailboxId") and not body.get("password"):
            # The saved password, only ever with the saved server and user.
            saved = mailbox_for(member, int(body["mailboxId"]))
            account = services.account_of(saved)
        else:
            if body.get("security", "ssl") not in SECURITY:
                return api_error("VALIDATION_ERROR", "security is ssl or starttls", 400)
            account = imap.Account(
                host=str(body.get("host") or ""),
                port=int(body.get("port") or 993),
                security=body.get("security", "ssl"),
                username=str(body.get("username") or ""),
                password=str(body.get("password") or ""),
            )
        folders = services.test_account(account)
    except (TypeError, ValueError):
        return api_error("VALIDATION_ERROR", "Check the server settings", 400)
    except imap.ImapError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200
    return jsonify({"ok": True, "folders": folders}), 200


@inbox_bp.post("/mailboxes/<int:mailbox_id>/sync")
@permission_required("messages", "read", "Read the shared inbox")
def sync_mailbox(mailbox_id: int):
    mailbox = mailbox_for(get_current_member(), mailbox_id)
    result = services.sync_mailbox(mailbox)
    db.session.commit()
    return jsonify(
        {
            **result,
            "mailbox": mailbox_to_dict(mailbox, can_manage(get_current_member())),
        }
    ), 200


# ── Messages ─────────────────────────────────────────────────────────────────


@inbox_bp.get("/messages")
@permission_required("messages", "read", "Read the shared inbox")
def list_messages():
    done = request.args.get("done")
    messages = MessageService.list_for(
        get_current_member(),
        request.args.get("mailbox_id", type=int),
        request.args.get("q"),
        None if done is None else done in ("1", "true"),
        request.args.get("before_id", type=int),
        request.args.get("limit", default=50, type=int),
    )
    return jsonify([message_to_dict(m) for m in messages]), 200


@inbox_bp.get("/messages/<int:message_id>")
@permission_required("messages", "read", "Read the shared inbox")
def get_message(message_id: int):
    message = message_for(get_current_member(), message_id)
    thread = MessageService.thread(message)
    return jsonify(
        {
            **message_to_dict(message, full=True),
            "thread": [message_to_dict(m, full=True) for m in thread],
        }
    ), 200


@inbox_bp.patch("/messages/<int:message_id>")
@permission_required("messages", "read", "Read the shared inbox")
def update_message(message_id: int):
    message = message_for(get_current_member(), message_id)
    body = _body()
    if "done" in body:
        message.done = bool(body["done"])
    db.session.commit()
    return jsonify(message_to_dict(message)), 200


@inbox_bp.get("/messages/<int:message_id>/attachments/<int:index>")
@permission_required("messages", "read", "Read the shared inbox")
def get_attachment(message_id: int, index: int):
    message = message_for(get_current_member(), message_id)
    filename, _content_type, data = MessageService.attachment(message, index)
    # Always a download: an attached HTML or SVG file never renders in the app.
    return send_file(
        io.BytesIO(data),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=filename,
    )
