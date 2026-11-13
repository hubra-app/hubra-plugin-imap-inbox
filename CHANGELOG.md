# Changelog

## 1.3.0

Security review (2026-11):

- An API token scoped to reading the inbox no longer sees every mailbox or
  the server settings because its owner manages mailboxes.
- Readers no longer see server names or the server's answer when a sync or
  an attachment download fails; the details go to the log.
- A member who only reads may start a sync once a minute (each one is a
  login at the club's mail server); managers are not held.
- Private addresses hidden inside IPv6 (::ffff:10.0.0.1, NAT64, 6to4,
  Teredo) are refused like plain private ones.
- Attachment file names lose folders, control characters and leading dots.
- `groupId` must be a number; the server's login error never reaches the
  log as a chained exception.
- Needs Hubra 0.2.1 or later (the dashboard widget contract); 0.2.0 failed
  to load the plugin.
- Mailbox dialog: Abbrechen outlined like other dialogs, Enter saves.
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
