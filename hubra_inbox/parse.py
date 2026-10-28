"""Turn a raw RFC 5322 message into what the inbox shows."""

from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime

import nh3

MAX_TEXT = 200_000

# Tags a mail body may keep.  No scripts, styles, forms, frames or media;
# images only from inline parts or data: URLs (remote ones are tracking
# pixels more often than not).
_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "caption",
    "center",
    "code",
    "col",
    "colgroup",
    "dd",
    "del",
    "div",
    "dl",
    "dt",
    "em",
    "font",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "ins",
    "li",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "small",
    "span",
    "strike",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
_ATTRS = {
    "*": {"align", "dir", "title", "colspan", "rowspan", "width", "height"},
    "a": {"href"},
    "img": {"src", "alt"},
    "font": {"color"},
}


@dataclass
class Parsed:
    message_id: str | None
    thread_key: str | None
    subject: str | None
    from_name: str | None
    from_address: str | None
    to_addresses: str | None
    cc_addresses: str | None
    sent_at: datetime | None
    text_body: str | None = None
    html_body: str | None = None
    attachments: list[dict] = field(default_factory=list)


def sanitise_html(html: str) -> str:
    def keep_url(tag: str, attr: str, value: str) -> str | None:
        if tag == "img" and attr == "src":
            return value if value.startswith(("cid:", "data:image/")) else None
        if tag == "a" and attr == "href":
            return (
                value if value.startswith(("https://", "http://", "mailto:")) else None
            )
        return value

    return nh3.clean(
        html[: MAX_TEXT * 5],
        tags=_TAGS,
        attributes=_ATTRS,
        url_schemes={"http", "https", "mailto", "cid", "data"},
        attribute_filter=keep_url,
        link_rel="noopener noreferrer nofollow",
        strip_comments=True,
    )


def _header(msg: EmailMessage, name: str) -> str | None:
    try:
        value = msg.get(name)
    except Exception:  # noqa: BLE001 - malformed headers are common
        return None
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _addresses(msg: EmailMessage, name: str) -> str | None:
    raw = msg.get_all(name) or []
    pairs = getaddresses([str(v) for v in raw])
    text = ", ".join(f"{n} <{a}>" if n else a for n, a in pairs if a)
    return text[:5000] or None


def _date(msg: EmailMessage) -> datetime | None:
    raw = _header(msg, "Date")
    if not raw:
        return None
    try:
        value = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _msgid(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"<[^<>]+>", value)
    found = m.group(0) if m else value
    return re.sub(r"\s+", "", found)[:255] or None


def _decode(part) -> str:
    try:
        content = part.get_content()
    except Exception:  # noqa: BLE001 - unknown charsets and broken encodings
        payload = part.get_payload(decode=True) or b""
        content = payload.decode("utf-8", "replace")
    return content if isinstance(content, str) else ""


def parse(raw: bytes) -> Parsed:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    from_pairs = getaddresses([str(v) for v in (msg.get_all("From") or [])])
    from_name, from_address = from_pairs[0] if from_pairs else ("", "")
    message_id = _msgid(_header(msg, "Message-ID"))
    references = (_header(msg, "References") or "").split()
    in_reply_to = _msgid(_header(msg, "In-Reply-To"))
    thread_key = _msgid(references[0]) if references else in_reply_to or message_id

    out = Parsed(
        message_id=message_id,
        thread_key=thread_key,
        subject=(_header(msg, "Subject") or "")[:500] or None,
        from_name=(from_name or "")[:255] or None,
        from_address=(from_address or "")[:320] or None,
        to_addresses=_addresses(msg, "To"),
        cc_addresses=_addresses(msg, "Cc"),
        sent_at=_date(msg),
    )
    if not msg.is_multipart() and msg.get_content_maintype() != "text":
        return out

    body = msg.get_body(preferencelist=("plain",))
    if body is not None:
        out.text_body = _decode(body)[:MAX_TEXT]
    html = msg.get_body(preferencelist=("html",))
    if html is not None:
        out.html_body = sanitise_html(_decode(html))[: MAX_TEXT * 2]
    if out.text_body is None and out.html_body:
        out.text_body = nh3.clean(out.html_body, tags=set())[:MAX_TEXT]

    for index, part in enumerate(msg.walk()):
        if part.is_multipart() or part in (body, html):
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if not filename and disposition != "attachment":
            continue
        payload = part.get_payload(decode=True) or b""
        out.attachments.append(
            {
                "index": index,
                "filename": (filename or f"attachment-{index}")[:255],
                "contentType": part.get_content_type(),
                "size": len(payload),
            }
        )
    return out


def attachment(raw: bytes, index: int) -> tuple[str, str, bytes] | None:
    """(filename, content type, bytes) of the walk() part at *index*."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    for i, part in enumerate(msg.walk()):
        if i == index and not part.is_multipart():
            return (
                part.get_filename() or f"attachment-{index}",
                part.get_content_type(),
                part.get_payload(decode=True) or b"",
            )
    return None
