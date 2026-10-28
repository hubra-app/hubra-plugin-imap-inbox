"""inbox_mailboxes and inbox_messages

Revision ID: 5b1e0c7d9a42
Revises:
Create Date: 2026-10-28 13:00:00

"""

from alembic import op
import sqlalchemy as sa

from hubra.core.plugins.ops import has_table


# revision identifiers, used by Alembic.
revision = "5b1e0c7d9a42"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    if not has_table("inbox_mailboxes"):
        op.create_table(
            "inbox_mailboxes",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("host", sa.String(length=255), nullable=False),
            sa.Column("port", sa.Integer(), nullable=False),
            sa.Column("security", sa.String(length=10), nullable=False),
            sa.Column("username", sa.String(length=255), nullable=False),
            sa.Column("password_encrypted", sa.Text(), nullable=False),
            sa.Column("folders", sa.JSON(), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=True),
            sa.Column(
                "mark_seen", sa.Boolean(), server_default=sa.false(), nullable=False
            ),
            sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("retention_days", sa.Integer(), nullable=False),
            sa.Column("sync_state", sa.JSON(), nullable=False),
            sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not has_table("inbox_messages"):
        op.create_table(
            "inbox_messages",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("mailbox_id", sa.Integer(), nullable=False),
            sa.Column("folder", sa.String(length=255), nullable=False),
            sa.Column("uid", sa.BigInteger(), nullable=False),
            sa.Column("uidvalidity", sa.BigInteger(), nullable=False),
            sa.Column("message_id", sa.String(length=255), nullable=True),
            sa.Column("thread_key", sa.String(length=255), nullable=True),
            sa.Column("subject", sa.String(length=500), nullable=True),
            sa.Column("from_name", sa.String(length=255), nullable=True),
            sa.Column("from_address", sa.String(length=320), nullable=True),
            sa.Column("to_addresses", sa.Text(), nullable=True),
            sa.Column("cc_addresses", sa.Text(), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("text_body", sa.Text(), nullable=True),
            sa.Column("html_body", sa.Text(), nullable=True),
            sa.Column("attachments", sa.JSON(), nullable=False),
            sa.Column("size", sa.Integer(), nullable=False),
            sa.Column(
                "truncated", sa.Boolean(), server_default=sa.false(), nullable=False
            ),
            sa.Column("done", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["mailbox_id"], ["inbox_mailboxes.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "mailbox_id",
                "folder",
                "uidvalidity",
                "uid",
                name="uq_inbox_message_uid",
            ),
        )
        with op.batch_alter_table("inbox_messages", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_inbox_messages_mailbox_id"), ["mailbox_id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_inbox_messages_thread_key"), ["thread_key"], unique=False
            )


def downgrade():
    op.drop_table("inbox_messages")
    op.drop_table("inbox_mailboxes")
