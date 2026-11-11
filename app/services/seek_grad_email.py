"""Parse forwarded SEEK Grad job-alert emails without following tracking links."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from email import policy
from email.parser import Parser
from html.parser import HTMLParser
from urllib.parse import urlparse

TRACKED_LINK = re.compile(
    r"<(?P<url>https?://[^>\s]*gradconnection\.com/track-link/[^>\s]+)>\s*(?P<label>.*)",
    re.IGNORECASE,
)
TRACK_ID = re.compile(r"/track-link/([^/?#]+)", re.IGNORECASE)
OTHER_LOCATIONS = re.compile(r"\b\d+\s+other locations?\b", re.IGNORECASE)
LOCATION_MARKER = re.compile(
    r"\b(?:Melbourne|Sydney|Canberra|Brisbane|Perth|Adelaide|Hobart|Darwin|VIC|NSW|QLD|WA|SA|TAS|NT|ACT)\b",
    re.IGNORECASE,
)


class SeekEmailParseError(ValueError):
    """The forwarded message did not match the supported SEEK Grad alert format."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    children: list[_Node | str] = field(default_factory=list)


class _TreeBuilder(HTMLParser):
    VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(
            tag.casefold(),
            {key.casefold(): value or "" for key, value in attrs},
            self.stack[-1],
        )
        self.stack[-1].children.append(node)
        if tag.casefold() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag.casefold():
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].children.append(data)


def _nodes(node: _Node, tag: str) -> list[_Node]:
    found = []
    for child in node.children:
        if isinstance(child, _Node):
            if child.tag == tag:
                found.append(child)
            found.extend(_nodes(child, tag))
    return found


def _node_text(node: _Node) -> str:
    parts: list[str] = []

    def visit(current: _Node) -> None:
        for child in current.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag in {"br", "p", "div", "h1", "h2", "h3", "li"}:
                parts.append(" ")
                visit(child)
                parts.append(" ")
            else:
                visit(child)

    visit(node)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _closing_date(text: str) -> date | None:
    match = re.search(
        r"Closing:\s*(?:\d{1,2}:\d{2}\s*[AP]M,\s*)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    for month_format in ("%B", "%b"):
        try:
            month = match.group(2)[:3] if month_format == "%b" else match.group(2)
            return datetime.strptime(
                f"{match.group(1)} {month} {match.group(3)}",
                f"%d {month_format} %Y",
            ).date()
        except ValueError:
            continue
    return None


def _parse_html_cards(content: str) -> list[dict[str, str | None]]:
    parser = _TreeBuilder()
    parser.feed(content)
    candidates: list[dict[str, str | None]] = []
    seen_ids: set[str] = set()
    for heading in _nodes(parser.root, "h2"):
        links = [
            link
            for link in _nodes(heading, "a")
            if link.attrs.get("title", "").casefold().startswith("apply to ")
        ]
        if not links:
            continue
        link = links[0]
        url = html.unescape(link.attrs.get("href", "")).replace("&amp;", "&")
        parsed_url = urlparse(url)
        link_id = TRACK_ID.search(parsed_url.path)
        if (
            not link_id
            or parsed_url.scheme != "https"
            or parsed_url.hostname != "au.gradconnection.com"
            or link_id.group(1) in seen_ids
        ):
            continue
        seen_ids.add(link_id.group(1))
        title = link.attrs["title"][len("Apply to ") :].strip()
        card = heading.parent
        while card is not None and card.tag != "td":
            card = card.parent
        if card is None:
            continue
        paragraph_texts = [_node_text(p) for p in _nodes(card, "p")]
        meaningful = [text for text in paragraph_texts if text and text != title]
        company = next(
            (
                text
                for text in meaningful
                if not text.casefold().startswith("closing:")
                and not OTHER_LOCATIONS.search(text)
                and not LOCATION_MARKER.search(text)
                and text.casefold() != "accept internationals"
            ),
            None,
        )
        location = next(
            (
                text
                for text in meaningful
                if OTHER_LOCATIONS.search(text) or LOCATION_MARKER.search(text)
            ),
            None,
        )
        close = next((parsed for text in meaningful if (parsed := _closing_date(text))), None)
        candidates.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "original_url": url,
                "closing_date": close.isoformat() if close else None,
            }
        )
    return candidates


def _parse_plain_cards(content: str) -> list[dict[str, str | None]]:
    lines = [html.unescape(line).strip() for line in content.splitlines()]
    candidates: list[dict[str, str | None]] = []
    seen_ids: set[str] = set()
    for index, line in enumerate(lines):
        match = TRACKED_LINK.search(line)
        if not match:
            continue
        url = match.group("url").rstrip(".,;)")
        label = re.sub(r"\s+", " ", match.group("label")).strip()
        if not label or OTHER_LOCATIONS.search(label) or len(label) < 4:
            continue
        parsed_url = urlparse(url)
        link_id = TRACK_ID.search(parsed_url.path)
        if (
            not link_id
            or parsed_url.scheme != "https"
            or parsed_url.hostname != "au.gradconnection.com"
            or link_id.group(1) in seen_ids
        ):
            continue
        seen_ids.add(link_id.group(1))

        next_lines = []
        for raw_line in lines[index + 1 : index + 20]:
            if raw_line and "cdn.gradconnection.com" not in raw_line:
                cleaned = re.sub(r"<https?://[^>]+>", " ", raw_line)
                cleaned = re.sub(r"\s+", " ", cleaned).strip()
                if cleaned:
                    next_lines.append(cleaned)
        company = next(
            (
                text
                for text in next_lines
                if not text.casefold().startswith("closing:")
                and not OTHER_LOCATIONS.search(text)
                and not LOCATION_MARKER.search(text)
                and text.casefold() not in {"accept internationals", "view more jobs"}
            ),
            None,
        )
        location = next(
            (
                text
                for text in next_lines
                if OTHER_LOCATIONS.search(text) or LOCATION_MARKER.search(text)
            ),
            None,
        )
        closing = next((parsed for text in next_lines if (parsed := _closing_date(text))), None)
        candidates.append(
            {
                "title": label,
                "company": company,
                "location": location,
                "original_url": url,
                "closing_date": closing.isoformat() if closing else None,
            }
        )
    return candidates


def _extract_body(body: str) -> tuple[str | None, str | None]:
    try:
        message = Parser(policy=policy.default).parsestr(body)
        plain_body = None
        html_body = None
        parts = message.walk() if message.is_multipart() else [message]
        for part in parts:
            if part.get_content_maintype() == "multipart":
                continue
            content = part.get_content()
            if not isinstance(content, str):
                continue
            if part.get_content_type() == "text/html":
                html_body = content
            elif part.get_content_type() == "text/plain":
                plain_body = content
        return plain_body, html_body
    except (TypeError, ValueError, LookupError):
        return body, None


def parse_seek_grad_email(body: str, today: date | None = None) -> dict[str, object]:
    """Extract job cards from pasted text, HTML, or a downloaded ``.eml`` message.

    Tracking links are recorded but never followed. Expired cards are reported and
    excluded from the import preview.
    """
    plain_body, html_body = _extract_body(body)
    candidates = _parse_html_cards(html_body) if html_body else []
    if not candidates and plain_body:
        candidates = _parse_plain_cards(plain_body)
    if not candidates and "<" in body and "/track-link/" in body:
        candidates = _parse_html_cards(body)
    if not candidates:
        raise SeekEmailParseError(
            "No SEEK Grad job cards were found. Paste the message body or upload "
            "the downloaded .eml file."
        )

    today = today or date.today()
    expired = [
        item
        for item in candidates
        if item["closing_date"] and date.fromisoformat(item["closing_date"]) < today
    ]
    current = [item for item in candidates if item not in expired]
    return {"jobs": current, "expired_count": len(expired), "found_count": len(candidates)}
