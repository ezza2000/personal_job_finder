"""Parse Prosple job-alert emails into the common import row shape."""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from datetime import date
from email import policy
from email.parser import Parser
from html.parser import HTMLParser

from app.services.prosple_rss import _posted_date


class ProspleEmailParseError(ValueError):
    """The supplied email did not contain supported Prosple job cards."""


class _EmailHTML(HTMLParser):
    """Collect visible text offsets and links from an email HTML body."""

    _BLOCKS = {"br", "div", "h1", "h2", "h3", "li", "p", "td", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[dict[str, object]] = []
        self.stack: list[dict[str, object]] = []
        self.hidden_depth = 0

    @property
    def text_offset(self) -> int:
        return sum(map(len, self.parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag in {"script", "style", "head"}:
            self.hidden_depth += 1
        if tag == "a" and attrs_map.get("href"):
            self.stack.append({"href": attrs_map["href"], "start": self.text_offset, "text": []})
        if tag in self._BLOCKS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.stack:
            item = self.stack.pop()
            item["end"] = self.text_offset
            item["text"] = " ".join(item["text"])
            self.links.append(item)
        if tag in {"script", "style", "head"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        if tag in self._BLOCKS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        cleaned = data.replace("\xa0", " ")
        self.parts.append(cleaned)
        for link in self.stack:
            link["text"].append(cleaned)

    def text(self) -> str:
        return re.sub(r"[ \t\r\f\v]+", " ", "".join(self.parts))


def _target_url(url: str) -> str | None:
    """Unwrap Prosple's Customer.io redirect and remove email tracking parameters."""
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname and parsed.hostname.casefold() == "e.customeriomail.com":
        pieces = parsed.path.split("/")
        try:
            token = pieces[pieces.index("c") + 1]
            padded = token.replace("-", "+").replace("_", "/")
            padded += "=" * ((4 - len(padded) % 4) % 4)
            payload = json.loads(base64.b64decode(padded).decode("utf-8"))
            url = str(payload.get("href", ""))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError, IndexError):
            return None

    target = urllib.parse.urlparse(url)
    if (
        target.scheme != "https"
        or target.hostname != "au.prosple.com"
        or "/graduate-employers/" not in target.path
        or "/jobs-internships/" not in target.path
    ):
        return None
    # Keep Prosple's stable listing id while dropping campaign and recipient tracking.
    job_id = urllib.parse.parse_qs(target.query).get("_j_id", [None])[0]
    query = urllib.parse.urlencode({"_j_id": job_id}) if job_id else ""
    return urllib.parse.urlunparse(target._replace(query=query, fragment=""))


def _html_from_message(raw: str) -> str:
    message = Parser(policy=policy.default).parsestr(raw)
    if not message.is_multipart():
        if message.get_content_type() == "text/html":
            return message.get_content()
        return ""
    for part in message.walk():
        if part.get_content_type() == "text/html" and not part.get_filename():
            try:
                return part.get_content()
            except (LookupError, UnicodeDecodeError):
                continue
    return ""


def parse_prosple_job_alert(content: str) -> dict[str, object]:
    """Parse raw MIME or HTML from a Prosple daily job alert."""
    html = (
        _html_from_message(content)
        if "MIME-Version:" in content or "Content-Type:" in content
        else content
    )
    if not html or "<" not in html:
        raise ProspleEmailParseError("No HTML Prosple job-alert content was found")

    parser = _EmailHTML()
    parser.feed(html)
    # Preserve character offsets used by anchor regions; HTMLParser has already
    # decoded entities, while block boundaries contribute newline separators.
    text = "".join(parser.parts)
    title_links: list[dict[str, object]] = []
    for link in parser.links:
        target = _target_url(str(link["href"]))
        title = re.sub(r"\s+", " ", str(link["text"])).strip()
        if not target or not title:
            continue
        title_links.append({**link, "target": target, "title": title})

    # The logo, employer name, and position title link to the same item. The
    # position-title link is the one whose text differs from its employer link.
    title_candidates = []
    for link in title_links:
        title = str(link["title"])
        if re.search(r"graduate|coordinator|analyst|engineer|consultant|program", title, re.I):
            title_candidates.append(link)

    entries: list[dict[str, str | None]] = []
    seen_targets: set[str] = set()
    for index, link in enumerate(title_candidates):
        target = str(link["target"])
        if target in seen_targets:
            continue
        seen_targets.add(target)
        start, end = int(link["start"]), int(link["end"])
        next_start = min(
            (int(item["start"]) for item in title_candidates[index + 1 :]),
            default=len(text),
        )
        region = text[end:next_start]
        prior_company = next(
            (
                str(candidate["title"])
                for candidate in reversed(title_links)
                if candidate["target"] == target
                and candidate["title"].casefold() != str(link["title"]).casefold()
                and int(candidate["start"]) < start
            ),
            None,
        )
        salary_match = re.search(
            r"(?:AUD\s*)?\$?\s*[\d,.]+\s*(?:-\s*(?:AUD\s*)?\$?\s*[\d,.]+)?\s*k?\s*(?:/\s*(?:yr|year))?",
            region,
            re.I,
        )
        deadline_match = re.search(
            r"(?:Apply by|Applications close|Closing date)\s+([^\n]+)", region, re.I
        )
        deadline = _posted_date(deadline_match.group(1).strip()) if deadline_match else None
        if deadline and date.fromisoformat(deadline) < date.today():
            continue
        location_region = region[: salary_match.start()] if salary_match else region
        location_lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in location_region.splitlines()
            if line.strip()
        ]
        location = location_lines[-1] if location_lines else None
        if location and not re.search(
            r"\b(Melbourne|Sydney|Brisbane|Perth|Adelaide|Canberra|Hobart|Darwin|Australia|Remote|Victoria|Queensland|NSW|WA|SA|ACT|Tasmania)\b",
            location,
            re.I,
        ):
            location = None
        entries.append(
            {
                "title": str(link["title"]),
                "company": prior_company,
                "location": location,
                "salary": re.sub(r"\s+", " ", salary_match.group(0)).strip()
                if salary_match
                else None,
                "employment_type": "Graduate program"
                if re.search(r"graduate", str(link["title"]), re.I)
                else None,
                "description": "Prosple job alert listing.",
                "date_posted": None,
                "closing_date": deadline,
                "original_url": target,
                "source": "Prosple Email",
                "status": "new",
            }
        )

    return {
        "jobs": entries,
        "found_count": len(seen_targets),
        "expired_count": len(seen_targets) - len(entries),
    }
