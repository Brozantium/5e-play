"""Small, defensive HTML inventory parser used alongside Scrapling responses."""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit


class PageInventoryParser(HTMLParser):
    """Extracts page structure without executing scripts or submitting forms."""

    def __init__(self, base_url: str, max_text_chars: int = 24000) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.max_text_chars = max_text_chars
        self.title_parts: list[str] = []
        self.description = ""
        self.canonical = ""
        self.headings: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.json_ld: list[Any] = []
        self.text_parts: list[str] = []
        self.buttons: list[str] = []
        self._title_depth = 0
        self._heading_depth = 0
        self._heading_tag = ""
        self._heading_parts: list[str] = []
        self._button_depth = 0
        self._button_parts: list[str] = []
        self._script_type = ""
        self._script_depth = 0
        self._script_parts: list[str] = []
        self._skip_text_depth = 0
        self._skip_tags = {"style", "noscript", "svg", "template"}

    def _absolute(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            return ""
        absolute = urljoin(self.base_url, value)
        parts = urlsplit(absolute)
        if parts.scheme not in {"http", "https"}:
            return ""
        return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        tag = tag.lower()

        if tag in self._skip_tags:
            self._skip_text_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag in {"h1", "h2", "h3"}:
            self._heading_depth += 1
            self._heading_tag = tag
            self._heading_parts = []
        if tag == "button":
            self._button_depth += 1
            self._button_parts = []

        if tag == "meta":
            name = (a.get("name") or a.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.description:
                self.description = a.get("content", "")[:1000]
        elif tag == "link":
            rel = a.get("rel", "").lower()
            href = self._absolute(a.get("href", ""))
            if rel == "canonical" and href:
                self.canonical = href
            if "stylesheet" in rel.split() and href:
                self.stylesheets.append(href)
        elif tag in {"a", "area"}:
            href = self._absolute(a.get("href", ""))
            if href:
                self.links.append({"url": href, "text": "", "rel": a.get("rel", "")})
        elif tag in {"img", "source"}:
            src = self._absolute(a.get("src", ""))
            if not src and a.get("srcset"):
                src = self._absolute(a.get("srcset", "").split(",")[0].strip().split(" ")[0])
            if src:
                self.images.append({
                    "url": src,
                    "alt": a.get("alt", "")[:500],
                    "mime_hint": a.get("type", "")[:100],
                })
        elif tag == "script":
            self._script_depth += 1
            self._script_type = a.get("type", "").lower()
            self._script_parts = []
            src = self._absolute(a.get("src", ""))
            if src:
                self.scripts.append(src)

        # Track useful non-sensitive interface labels only; never collect form values.
        if tag in {"button", "input", "select", "textarea"}:
            label = a.get("aria-label") or a.get("placeholder") or a.get("title") or a.get("type") or tag
            if label:
                self.buttons.append(f"{tag}: {label[:120]}")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._skip_tags and self._skip_text_depth:
            self._skip_text_depth -= 1
        if tag == "title" and self._title_depth:
            self._title_depth -= 1
        if tag in {"h1", "h2", "h3"} and self._heading_depth:
            value = " ".join(" ".join(self._heading_parts).split())
            if value:
                self.headings.append({"level": self._heading_tag, "text": value[:500]})
            self._heading_depth -= 1
        if tag == "button" and self._button_depth:
            value = " ".join(" ".join(self._button_parts).split())
            if value:
                self.buttons.append(f"button text: {value[:120]}")
            self._button_depth -= 1
        if tag == "script" and self._script_depth:
            if "ld+json" in self._script_type:
                raw = "".join(self._script_parts).strip()
                if raw:
                    # Preserve raw JSON-LD as text; don't execute or trust it.
                    self.json_ld.append(raw[:100000])
            self._script_depth -= 1
            self._script_type = ""
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._title_depth:
            self.title_parts.append(data)
        if self._heading_depth:
            self._heading_parts.append(data)
        if self._button_depth:
            self._button_parts.append(data)
        if self._script_depth:
            self._script_parts.append(data)
        if not self._skip_text_depth and not self._script_depth:
            clean = " ".join(data.split())
            if clean:
                self.text_parts.append(clean)

    def result(self) -> dict[str, Any]:
        text = " ".join(self.text_parts)
        return {
            "title": " ".join(" ".join(self.title_parts).split())[:500],
            "description": self.description,
            "canonical_url": self.canonical,
            "headings": self.headings[:120],
            "text_excerpt": text[: self.max_text_chars],
            "links": self.links,
            "images": self.images,
            "script_sources": sorted(set(self.scripts)),
            "stylesheets": sorted(set(self.stylesheets)),
            "json_ld_raw": self.json_ld,
            "interface_labels": self.buttons[:250],
        }


def extract_inventory(html: str, base_url: str, max_text_chars: int) -> dict[str, Any]:
    parser = PageInventoryParser(base_url=base_url, max_text_chars=max_text_chars)
    parser.feed(html)
    parser.close()
    return parser.result()
