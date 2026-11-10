# Changelog

## Unreleased

- The menu entry moves to the new sidebar area **Kommunikation**, next to Mail,
  Letters and Messengers. Needs a Hubra with that area (after 0.2.5); older
  versions show it under a heading of its own.
- Dashboard widget **Offene Mails**: mails not marked done yet, newest first, from the mailboxes the member may read (needs `inbox.messages.read`).
- German texts are in Standard German now; they were still in Swiss German dialect.

## 1.2.0

The mailbox set-up moved from the "Mailboxes" dialog to the page's last tab,
Posteingang › Einstellungen (`/app/inbox/settings`), shown to those who may
manage mailboxes. Each mailbox is still edited in its own dialog. This
follows Hubra's rule that a setting lives on the page it configures.
- Dashboard widget **Offene Mails**: mails not marked done yet, newest first, from the mailboxes the member may read (needs `inbox.messages.read`).

## 1.1.0

Built for Hubra 0.2 (Mantine 9, plugin host API 2). Needs Hubra 0.2 or newer.

## 1.0.1

- One mailbox that drops the connection or answers with an IMAP error no
  longer stops the sync of every later mailbox of the club. The error is
  shown on that mailbox, and the others sync as usual.
- The search date no longer depends on the server's locale.
- The text of an HTML-only mail shows & and < instead of &amp; and &lt;.
- A sender's Date header no longer decides retention or keeps a message
  on top: old-dated mail is kept for the retention period from when it
  was fetched, and a future date counts as now.
- A mailbox deleted while the sync runs no longer stops the sync of the
  club's other mailboxes.

## 1.0.0

First release.

- Connect club mailboxes hosted anywhere over IMAP (TLS on 993, or STARTTLS
  on 143) with a password or an app password.
- Each mailbox is visible to the members of one group (for example the
  board); people with "Set up shared mailboxes" see and manage all of them.
- Passwords are encrypted before they are stored and never sent back to the
  browser. Changing the server or user name needs the password again, so a
  stored password can't be sent to another server.
- Read-only by default: folders are opened with EXAMINE and messages read
  with BODY.PEEK, so Hubra never marks mail as read, moves or deletes it.
- New mail is fetched every five minutes, or on "Sync now". The first sync
  reads the messages of the retention period (default 180 days); older
  messages are removed from Hubra, never from the server.
- HTML mail is cleaned (no scripts, styles, forms or remote images) and shown
  in a sandboxed frame. Attachments are fetched from the server when opened
  and always downloaded, never shown inline.
- Mail servers in private networks are refused unless the operator sets
  `INBOX_ALLOW_PRIVATE_HOSTS=true`.
