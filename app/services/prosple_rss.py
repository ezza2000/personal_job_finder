"""Fetch and normalize public Prosple RSS items without scraping job pages."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from ipaddress import ip_address
from socket import getaddrinfo

MAX_FEED_BYTES = 2_000_000
TIMEOUT_SECONDS = 12


class FeedImportError(ValueError):
    """A configured Prosple feed could not be safely fetched or parsed."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class _AllowedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts: set[str]) -> None:
        self.hosts = hosts

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.hosts)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _allowed_host(hostname: str, allowed_hosts: set[str]) -> bool:
    host = hostname.casefold().rstrip(".")
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)


def _validate_url(url: str, allowed_hosts: set[str]) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise FeedImportError(
            "The Prosple RSS URL must be an HTTPS URL without embedded credentials"
        )
    host = parsed.hostname.casefold().rstrip(".")
    if not _allowed_host(host, allowed_hosts):
        raise FeedImportError(f"RSS host '{host}' is not in the configured allowlist")
    try:
        resolved = getaddrinfo(host, parsed.port or 443, type=0)
        if any(not ip_address(address[4][0]).is_global for address in resolved):
            raise FeedImportError("RSS host resolved to a non-public IP address")
    except OSError as exc:
        raise FeedImportError("RSS host could not be resolved") from exc
    return parsed


def _text(element: ET.Element, *names: str) -> str | None:
    wanted = {name.casefold() for name in names}
    for child in element.iter():
        if child is element:
            continue
        tag = child.tag.rsplit("}", 1)[-1].casefold()
        if tag in wanted:
            value = child.attrib.get("href") or "".join(child.itertext())
            value = html.unescape(value).strip()
            if value:
                return value
    return None


def _plain_text(value: str | None) -> str | None:
    if not value:
        return None
    extractor = _TextExtractor()
    extractor.feed(value)
    cleaned = re.sub(r"\s+", " ", " ".join(extractor.parts)).strip()
    return cleaned or None


def _posted_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            try:
                return date.fromisoformat(value[:10]).isoformat()
            except ValueError:
                return None


def _items(root: ET.Element) -> list[ET.Element]:
    result = [
        element
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1].casefold() in {"item", "entry"}
    ]
    return result[:1000]


def _normalize_item(item: ET.Element) -> dict[str, str | None] | None:
    title = _text(item, "title")
    url = _text(item, "link", "guid")
    if not url or url.startswith("/"):
        return None
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in {"https", "http"} or not parsed_url.hostname:
        return None

    company = _text(item, "company", "employer", "organization", "creator", "author")
    if title and not company:
        match = re.match(r"^(.+?)\s+(?:at|@)\s+(.+)$", title, re.IGNORECASE)
        if match:
            title, company = match.group(1).strip(), match.group(2).strip()
    if title:
        title = re.sub(r"\s+", " ", title).strip()
    if company:
        company = re.sub(r"\s+", " ", company).strip()

    return {
        "title": title,
        "company": company,
        "location": _text(item, "location", "joblocation", "city"),
        "salary": _text(item, "salary", "salarytext", "remuneration"),
        "employment_type": _text(item, "employmenttype", "jobtype", "employment"),
        "description": _plain_text(_text(item, "description", "summary", "encoded", "content")),
        "date_posted": _posted_date(_text(item, "pubdate", "published", "updated", "date")),
        "original_url": url,
        "source": "Prosple RSS",
        "status": "new",
    }


def parse_prosple_feed(content: bytes) -> list[dict[str, str | None]]:
    """Parse RSS or Atom XML into the import preview row shape."""
    if len(content) > MAX_FEED_BYTES:
        raise FeedImportError("The RSS feed exceeds the 2 MB size limit")
    upper = content[:4096].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FeedImportError("RSS feeds containing DTD or entity declarations are not accepted")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise FeedImportError("The configured feed is not valid RSS or Atom XML") from exc
    items = _items(root)
    if not items:
        raise FeedImportError("The feed did not contain RSS items or Atom entries")
    return [normalized for item in items if (normalized := _normalize_item(item)) is not None]


def fetch_prosple_feed(url: str, allowed_hosts: set[str]) -> list[dict[str, str | None]]:
    """Fetch a configured feed from an allowlisted public HTTPS host."""
    parsed = _validate_url(url, allowed_hosts)
    # Public DNS names are required; reject literal IPs and any private DNS answers above.
    try:
        ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise FeedImportError("RSS feed URLs must use a public domain name, not an IP address")

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
            "User-Agent": "PersonalJobFinder/0.1 (+local job search tool)",
        },
    )
    opener = urllib.request.build_opener(_AllowedRedirect(allowed_hosts))
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            content = response.read(MAX_FEED_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise FeedImportError("Could not fetch the configured RSS feed") from exc
    return parse_prosple_feed(content)
