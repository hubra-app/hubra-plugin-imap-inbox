"""Shared inbox: read external IMAP mailboxes (info@, vorstand@...) in Hubra."""

from hubra.core.modules import Blueprint, Module, NavItem, Schedule

module = Module(
    code="inbox",
    name="Shared inbox",
    description="Read the club's mailboxes (IMAP) in Hubra, each visible to one group",
    default_enabled=False,
    depends_on=("members",),
    blueprints=(
        Blueprint(
            "hubra_inbox.routes",
            "inbox_bp",
            "/api/v1/inbox",
            v2=(("/api/v2/tenants/inbox", "inbox_bp_v2"),),
        ),
    ),
    nav=(
        NavItem(
            "/app/inbox",
            "shell.nav.inbox",
            "inbox",
            order=45,
            perms=("inbox.messages.read",),
        ),
    ),
    tables=("inbox_mailboxes", "inbox_messages"),
    tasks=("hubra_inbox.tasks",),
    schedule=(Schedule("inbox-sync-5min", "hubra_inbox.tasks.sync_all", 300.0),),
)
