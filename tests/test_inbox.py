"""inbox: mailboxes, encrypted passwords, read-only sync, visibility."""

from __future__ import annotations

from email.message import EmailMessage

import pytest

from tests.helpers import set_modules
from hubra.core.models.group import Group, GroupMembership
from hubra.core.models.member import Member
from hubra.core.models.user import User
from hubra_inbox import crypto, imap, parse, services
from hubra_inbox.models import InboxMailbox, InboxMessage


def _mail(
    subject,
    sender="Hans Muster <hans@example.ch>",
    msgid=None,
    refs=None,
    html=None,
    attach=False,
    date="Tue, 27 Oct 2026 10:00:00 +0100",
):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "info@club.ch"
    msg["Subject"] = subject
    msg["Date"] = date
    msg["Message-ID"] = (
        msgid or f"<{''.join(c for c in subject if c.isalnum())}@example.ch>"
    )
    if refs:
        msg["References"] = refs
        msg["In-Reply-To"] = refs.split()[-1]
    msg.set_content(f"Hallo, {subject}")
    if html:
        msg.add_alternative(html, subtype="html")
    if attach:
        msg.add_attachment(
            b"%PDF-1.4 test",
            maintype="application",
            subtype="pdf",
            filename="anmeldung.pdf",
        )
    return msg.as_bytes()


class FakeImap:
    """Enough of imaplib.IMAP4 for the sync, recording what was asked."""

    def __init__(self, folders):
        # folder -> (uidvalidity, {uid: raw})
        self.folders = folders
        self.selected = None
        self.calls = []

    def login(self, user, password):
        self.calls.append(("login", user, password))
        if password != "secret":
            raise imap.imaplib.IMAP4.error(f"AUTHENTICATIONFAILED for {password}")

    def select(self, mailbox, readonly=False):
        name = mailbox.strip('"')
        self.calls.append(("select", name, readonly))
        if name not in self.folders:
            return "NO", [b"no such folder"]
        self.selected = name
        return "OK", [b"1"]

    def response(self, code):
        return code, [str(self.folders[self.selected][0]).encode()]

    def uid(self, command, *args):
        validity, messages = self.folders[self.selected]
        self.calls.append(("uid", command, *args))
        if command == "SEARCH":
            criteria = args[-1]
            uids = sorted(messages)
            if criteria.startswith("UID "):
                low = int(criteria[4:].split(":")[0])
                uids = [u for u in uids if u >= low] or uids[-1:]
            return "OK", [" ".join(map(str, uids)).encode()]
        if command == "FETCH":
            uid, what = int(args[0]), args[1]
            raw = messages[uid]
            if what == "(RFC822.SIZE)":
                return "OK", [f"1 (UID {uid} RFC822.SIZE {len(raw)})".encode()]
            return "OK", [
                (f"1 (UID {uid} {what[1:-1]} {{{len(raw)}}}".encode(), raw),
                b")",
            ]
        raise AssertionError(command)

    def list(self):
        return "OK", [
            b'(\\HasNoChildren) "/" "INBOX"',
            b'(\\Noselect) "/" "[Gmail]"',
            b'(\\HasNoChildren) "/" "Archiv 2026"',
        ]

    def logout(self):
        self.calls.append(("logout",))


@pytest.fixture
def fake(monkeypatch):
    server = FakeImap(
        {"INBOX": (7, {1: _mail("Anmeldung"), 2: _mail("Frage Training")})}
    )

    # The real connect() runs, with the server swapped for the fake.
    monkeypatch.setattr(imap, "_PinnedSSL", lambda host, port, address, context: server)
    monkeypatch.setattr(imap, "resolve", lambda host, port: "203.0.113.10")
    return server


@pytest.fixture
def board(db, seeded_db):
    set_modules(True, "inbox")
    group = Group(name="Vorstand")
    db.session.add(group)
    db.session.commit()
    return group


def _create(client, **extra):
    body = {
        "name": "Info",
        "host": "imap.example.ch",
        "username": "info@club.ch",
        "password": "secret",
        **extra,
    }
    return client.post("/api/v1/inbox/mailboxes", json=body)


def test_password_is_encrypted_and_never_returned(
    client, db, auth_headers, board, fake
):
    resp = _create(client, groupId=board.id)
    assert resp.status_code == 201
    body = resp.get_json()
    assert "password" not in body and "passwordEncrypted" not in body
    assert body["hasPassword"] is True
    stored = db.session.get(InboxMailbox, body["id"])
    assert "secret" not in stored.password_encrypted
    assert crypto.decrypt(stored.password_encrypted) == "secret"
    listed = client.get("/api/v1/inbox/mailboxes").get_json()
    assert "secret" not in str(listed)


def test_sync_is_read_only_and_incremental(client, db, auth_headers, board, fake):
    mailbox_id = _create(client).get_json()["id"]
    resp = client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    assert resp.get_json()["fetched"] == 2
    # EXAMINE (read-only) and BODY.PEEK: nothing on the server changes.
    assert ("select", "INBOX", True) in fake.calls
    fetches = [c for c in fake.calls if c[:2] == ("uid", "FETCH")]
    assert all("PEEK" in c[3] or "SIZE" in c[3] for c in fetches)

    messages = client.get("/api/v1/inbox/messages").get_json()
    assert {m["subject"] for m in messages} == {"Anmeldung", "Frage Training"}

    # Only the new message is fetched next time.
    fake.folders["INBOX"][1][3] = _mail("Re: Anmeldung", refs="<Anmeldung@example.ch>")
    fake.calls.clear()
    assert (
        client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync").get_json()["fetched"]
        == 1
    )
    fetched_uids = {c[2] for c in fake.calls if c[:2] == ("uid", "FETCH")}
    assert fetched_uids == {"3"}

    reply = next(
        m
        for m in client.get("/api/v1/inbox/messages").get_json()
        if m["subject"] == "Re: Anmeldung"
    )
    detail = client.get(f"/api/v1/inbox/messages/{reply['id']}").get_json()
    assert [m["subject"] for m in detail["thread"]] == ["Anmeldung", "Re: Anmeldung"]

    # A sync with nothing new fetches nothing ("UID 4:*" returns the last one).
    assert (
        client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync").get_json()["fetched"]
        == 0
    )


def test_uidvalidity_change_starts_again(client, db, auth_headers, board, fake):
    mailbox_id = _create(client).get_json()["id"]
    client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    fake.folders["INBOX"] = (8, {1: _mail("Neu nummeriert")})
    client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    subjects = [m.subject for m in db.session.scalars(db.select(InboxMessage))]
    assert subjects == ["Neu nummeriert"]


def test_mark_seen_opens_read_write(client, db, auth_headers, board, fake):
    mailbox_id = _create(client, markSeen=True).get_json()["id"]
    client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    assert ("select", "INBOX", False) in fake.calls


def test_login_error_is_stored_without_the_password(
    client, db, auth_headers, board, fake
):
    mailbox_id = _create(client, password="wrong").get_json()["id"]
    body = client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync").get_json()
    assert body["mailbox"]["lastError"]
    assert "wrong" not in body["mailbox"]["lastError"]


def test_changing_the_server_needs_the_password(client, db, auth_headers, board, fake):
    mailbox_id = _create(client).get_json()["id"]
    resp = client.patch(
        f"/api/v1/inbox/mailboxes/{mailbox_id}", json={"host": "evil.example.com"}
    )
    assert resp.status_code == 400 and resp.get_json()["error"] == "PASSWORD_REQUIRED"
    ok = client.patch(
        f"/api/v1/inbox/mailboxes/{mailbox_id}",
        json={"host": "imap2.example.ch", "password": "secret"},
    )
    assert ok.status_code == 200
    # Renaming needs no password.
    assert (
        client.patch(
            f"/api/v1/inbox/mailboxes/{mailbox_id}", json={"name": "Infos"}
        ).status_code
        == 200
    )


def test_connection_test_lists_selectable_folders(client, auth_headers, board, fake):
    resp = client.post(
        "/api/v1/inbox/mailboxes/test",
        json={"host": "imap.example.ch", "username": "u", "password": "secret"},
    )
    assert resp.get_json() == {"ok": True, "folders": ["INBOX", "Archiv 2026"]}
    bad = client.post(
        "/api/v1/inbox/mailboxes/test",
        json={"host": "imap.example.ch", "username": "u", "password": "nope"},
    ).get_json()
    assert bad["ok"] is False and "nope" not in bad["error"]


def test_done_and_search(client, db, auth_headers, board, fake):
    mailbox_id = _create(client).get_json()["id"]
    client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    [hit] = client.get("/api/v1/inbox/messages?q=training").get_json()
    client.patch(f"/api/v1/inbox/messages/{hit['id']}", json={"done": True})
    open_ = client.get("/api/v1/inbox/messages?done=0").get_json()
    assert [m["subject"] for m in open_] == ["Anmeldung"]


def test_attachment_is_fetched_from_the_server(client, db, auth_headers, board, fake):
    fake.folders["INBOX"][1][5] = _mail("Mit Anhang", attach=True)
    mailbox_id = _create(client).get_json()["id"]
    client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    msg = next(
        m
        for m in client.get("/api/v1/inbox/messages").get_json()
        if m["hasAttachments"]
    )
    detail = client.get(f"/api/v1/inbox/messages/{msg['id']}").get_json()
    [att] = detail["attachments"]
    assert att["filename"] == "anmeldung.pdf"
    resp = client.get(f"/api/v1/inbox/messages/{msg['id']}/attachments/{att['index']}")
    assert resp.status_code == 200
    assert resp.data == b"%PDF-1.4 test"
    assert resp.mimetype == "application/octet-stream"
    assert "attachment" in resp.headers["Content-Disposition"]


def test_visibility_by_group(db, seeded_db, board, fake):
    set_modules(True, "inbox")
    user = User(email="m@test.ch", first_name="Mia", last_name="Muster")
    user.set_password("password123")
    db.session.add(user)
    db.session.flush()
    member = Member(user_id=user.id, status="active", tier_id=seeded_db["tier"].id)
    db.session.add(member)
    db.session.flush()
    board_box = InboxMailbox(
        name="Vorstand",
        host="h",
        username="u",
        password_encrypted=crypto.encrypt("x"),
        group_id=board.id,
        folders=["INBOX"],
        sync_state={},
    )
    private_box = InboxMailbox(
        name="Kasse",
        host="h",
        username="u",
        password_encrypted=crypto.encrypt("x"),
        folders=["INBOX"],
        sync_state={},
    )
    db.session.add_all([board_box, private_box])
    db.session.flush()
    assert services.visible_mailbox_ids(member) == set()
    db.session.add(GroupMembership(group_id=board.id, member_id=member.id))
    db.session.flush()
    assert services.visible_mailbox_ids(member) == {board_box.id}
    # Admins and inbox managers see every mailbox.
    assert services.visible_mailbox_ids(seeded_db["admin"]) == {
        board_box.id,
        private_box.id,
    }


def test_module_off(client, auth_headers, board):
    set_modules(False, "inbox")
    assert client.get("/api/v1/inbox/mailboxes").status_code == 403


# ── Units ────────────────────────────────────────────────────────────────────


def test_html_is_sanitised():
    html = (
        '<p onclick="x()">Hi<script>alert(1)</script></p>'
        '<img src="https://track.example/p.gif"><img src="cid:logo">'
        '<a href="javascript:alert(1)">x</a><a href="https://club.ch">ok</a>'
        "<style>body{}</style><form><input></form>"
    )
    clean = parse.sanitise_html(html)
    assert "script" not in clean and "onclick" not in clean and "style" not in clean
    assert "track.example" not in clean and 'src="cid:logo"' in clean
    assert "javascript" not in clean and 'href="https://club.ch"' in clean
    assert "<form" not in clean and "<input" not in clean


def test_parse_text_from_html_only_mail():
    msg = EmailMessage()
    msg["From"] = "Lisa <lisa@example.ch>"
    msg["Subject"] = "=?utf-8?q?Gr=C3=BCezi?="
    msg.set_content("<p>Nur <b>HTML</b> &amp; 3 &lt; 4</p>", subtype="html")
    p = parse.parse(msg.as_bytes())
    assert p.subject == "Grüezi"
    assert p.from_name == "Lisa" and p.from_address == "lisa@example.ch"
    assert "Nur" in p.text_body and "<b>" not in p.text_body
    assert "& 3 < 4" in p.text_body


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"]
)
def test_private_hosts_are_refused(app, host):
    with app.app_context(), pytest.raises(imap.ImapError):
        imap.resolve(host, 993)


def test_private_hosts_allowed_by_the_operator(app):
    app.config["INBOX_ALLOW_PRIVATE_HOSTS"] = True
    try:
        with app.app_context():
            assert imap.resolve("127.0.0.1", 993) == "127.0.0.1"
    finally:
        app.config.pop("INBOX_ALLOW_PRIVATE_HOSTS")


def test_bad_host_names(app):
    with app.app_context():
        for host in ("", "imap.example.ch/../x", "a b"):
            with pytest.raises(imap.ImapError):
                imap.resolve(host, 993)


def test_key_rotation(app):
    with app.app_context():
        token = crypto.encrypt("pw")
        old = app.config.get("FERNET_KEY") or app.config["SECRET_KEY"]
        app.config["FERNET_KEY"] = "a-new-key"
        app.config["FERNET_OLD_KEYS"] = old
        try:
            assert crypto.decrypt(token) == "pw"
            rotated = crypto.rotate(token)
            app.config["FERNET_OLD_KEYS"] = ""
            assert crypto.decrypt(rotated) == "pw"
            with pytest.raises(ValueError):
                crypto.decrypt(token)
        finally:
            app.config["FERNET_KEY"] = "" if old == app.config["SECRET_KEY"] else old
            app.config.pop("FERNET_OLD_KEYS", None)


def test_scheduled_sync(app, db, seeded_db, board, fake):
    from hubra_inbox.tasks import sync_all

    from hubra.core.tasks import celery_app

    schedule = celery_app.conf.beat_schedule
    assert schedule["inbox-sync-5min"]["task"] == "hubra_inbox.tasks.sync_all"
    db.session.add(
        InboxMailbox(
            name="Info",
            host="imap.example.ch",
            username="u",
            password_encrypted=crypto.encrypt("secret"),
            folders=["INBOX"],
            sync_state={},
        )
    )
    db.session.commit()
    result = sync_all.run()
    assert list(result.values())[0]["fetched"] == 2


def test_a_broken_mailbox_does_not_stop_the_others(db, board, fake, monkeypatch):
    class Dropped(FakeImap):
        def uid(self, command, *args):
            if command == "FETCH":
                raise imap.imaplib.IMAP4.abort("socket error: EOF")
            return super().uid(command, *args)

    broken = Dropped(fake.folders)
    monkeypatch.setattr(
        imap,
        "_PinnedSSL",
        lambda host, port, address, context: broken if host == "bad.example" else fake,
    )
    for name, host in (("A", "bad.example"), ("B", "good.example")):
        db.session.add(
            InboxMailbox(
                name=name,
                host=host,
                username="u",
                password_encrypted=crypto.encrypt("secret"),
                folders=["INBOX"],
                sync_state={},
            )
        )
    db.session.commit()

    services.sync_all()
    bad = db.session.query(InboxMailbox).filter_by(name="A").one()
    good = db.session.query(InboxMailbox).filter_by(name="B").one()
    assert "EOF" in bad.last_error
    assert good.last_error is None and good.last_sync_at is not None


def test_search_dates_do_not_depend_on_the_locale():
    from datetime import datetime

    assert services._imap_date(datetime(2026, 3, 5)) == "05-Mar-2026"


def test_sender_dates_do_not_drive_order_or_retention(
    client, db, auth_headers, board, fake
):
    fake.folders["INBOX"][1][3] = _mail(
        "Top forever", date="Fri, 01 Jan 2099 10:00:00 +0000"
    )
    fake.folders["INBOX"][1][4] = _mail("Old", date="Mon, 01 Jan 1990 10:00:00 +0000")
    mailbox_id = _create(client).get_json()["id"]
    client.post(f"/api/v1/inbox/mailboxes/{mailbox_id}/sync")
    by_subject = {
        m["subject"]: m for m in client.get("/api/v1/inbox/messages").get_json()
    }
    assert "Old" in by_subject
    assert by_subject["Top forever"]["sentAt"] < "2099"


def test_a_mailbox_deleted_during_sync_is_skipped(db, monkeypatch):
    calls = []
    real_get = db.session.get

    def vanishing_get(model, ident, *a, **kw):
        if model is InboxMailbox and ident == first_id:
            return None  # deleted between reading the ids and loading it
        return real_get(model, ident, *a, **kw)

    for name in ("Gone", "Kept"):
        db.session.add(
            InboxMailbox(
                name=name,
                host="x.example",
                username="u",
                password_encrypted=crypto.encrypt("secret"),
                folders=["INBOX"],
                sync_state={},
            )
        )
    db.session.commit()
    first_id, second_id = sorted(m.id for m in db.session.query(InboxMailbox))
    monkeypatch.setattr(db.session, "get", vanishing_get)
    monkeypatch.setattr(services, "sync_mailbox", lambda m: calls.append(m.id) or {})

    results = services.sync_all()
    assert calls == [second_id] and first_id not in results
