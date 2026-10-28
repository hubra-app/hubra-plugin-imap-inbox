# Changelog

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
