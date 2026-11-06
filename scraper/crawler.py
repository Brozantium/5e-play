"""Conservative same-site crawler using Scrapling fetchers."""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.robotparser import RobotFileParser

from .extract import extract_inventory
from .storage import ArchiveDB, json_dump, jsonl_append


class CrawlStopped(RuntimeError):
    pass


class RobotsPolicy:
    def __init__(self, config: dict[str, Any], logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.cache: dict[str, RobotFileParser | None] = {}
        self.crawl_delays: dict[str, float] = {}

    def _origin(self, url: str) -> str:
        p = urllib.parse.urlsplit(url)
        return f"{p.scheme}://{p.netloc}"

    def _load(self, url: str) -> RobotFileParser | None:
        origin = self._origin(url)
        if origin in self.cache:
            return self.cache[origin]
        robots_url = origin + "/robots.txt"
        parser = RobotFileParser(robots_url)
        request = urllib.request.Request(
            robots_url,
            headers={"User-Agent": self.config["project"]["user_agent"], "Accept": "text/plain,*/*;q=0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read(512_000).decode("utf-8", errors="replace")
            parser.parse(body.splitlines())
            self.cache[origin] = parser
            delay = parser.crawl_delay("*")
            if delay:
                self.crawl_delays[origin] = float(delay)
            return parser
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                parser.parse([])
                self.cache[origin] = parser
                return parser
            self.logger.warning("robots.txt returned HTTP %s for %s", exc.code, origin)
        except Exception as exc:  # network/DNS/timeout: fail closed by default
            self.logger.warning("Could not read robots.txt for %s: %s", origin, exc)
        self.cache[origin] = None
        return None

    def allowed(self, url: str) -> bool:
        target = self.config["target"]
        if not target.get("obey_robots_txt", True):
            return True
        parser = self._load(url)
        if parser is None:
            return not target.get("robots_fail_closed", True)
        ua = self.config["project"].get("user_agent") or "*"
        try:
            return parser.can_fetch(ua, url) and parser.can_fetch("*", url)
        except Exception:
            return not target.get("robots_fail_closed", True)

    def minimum_delay(self, url: str) -> float:
        origin = self._origin(url)
        configured = float(self.config["crawl"].get("delay_seconds", 2.5))
        return max(configured, self.crawl_delays.get(origin, 0.0))


class ScraplingCrawler:
    def __init__(self, config: dict[str, Any], run_dir: Path, logger: logging.Logger) -> None:
        self.config = config
        self.run_dir = run_dir
        self.logger = logger
        self.policy = RobotsPolicy(config, logger)
        self.target = config["target"]
        self.crawl = config["crawl"]
        self.asset_cfg = config["assets"]
        self.db = ArchiveDB(run_dir / "archive.sqlite3")
        self.pages: list[dict[str, Any]] = []
        self.all_links: list[dict[str, Any]] = []
        self.all_assets: list[dict[str, Any]] = []
        self.visited: set[str] = set()
        self.last_request_at = 0.0
        self.stop_requested = False
        self.saved_asset_count = 0
        self.http_fetcher = None
        self.dynamic_fetcher = None

    def _normalise_url(self, url: str) -> str | None:
        p = urllib.parse.urlsplit(url.strip())
        if p.scheme not in {"http", "https"} or not p.hostname:
            return None
        host = p.hostname.lower()
        allowed = {d.lower() for d in self.target.get("allowed_domains", [])}
        if host not in allowed:
            return None
        if p.username or p.password:
            return None
        path = p.path or "/"
        prefixes = self.target.get("path_prefixes") or ["/"]
        if not any(prefix == "*" or path.startswith(prefix) for prefix in prefixes):
            return None
        if any(path.startswith(prefix) for prefix in self.target.get("exclude_path_prefixes", [])):
            return None
        query = "" if self.target.get("drop_query_strings", True) else p.query
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))

    def _scrapling_fetch(self, url: str):
        mode = self.crawl.get("fetch_mode", "dynamic").lower()
        ua = self.config["project"]["user_agent"]
        timeout_s = int(self.crawl.get("timeout_seconds", 45))
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        }
        if mode == "http":
            from scrapling.fetchers import Fetcher
            return Fetcher.get(url, headers=headers, timeout=timeout_s)
        if mode == "dynamic":
            from scrapling.fetchers import DynamicFetcher
            options: dict[str, Any] = {
                "headless": True,
                "network_idle": bool(self.crawl.get("network_idle", False)),
                "timeout": timeout_s * 1000,
                "extra_headers": headers,
            }
            wait_selector = self.crawl.get("wait_selector")
            if wait_selector:
                options["wait_selector"] = wait_selector
            wait_ms = int(self.crawl.get("wait_after_load_ms", 0))
            if wait_ms:
                options["wait"] = wait_ms
            return DynamicFetcher.fetch(url, **options)
        raise ValueError(f"Unsupported fetch_mode: {mode!r}; use 'http' or 'dynamic'.")

    def _request(self, url: str):
        min_delay = self.policy.minimum_delay(url)
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)
        self.last_request_at = time.monotonic()
        return self._scrapling_fetch(url)

    @staticmethod
    def _safe_html(response: Any, max_bytes: int) -> tuple[bytes, str]:
        body = getattr(response, "body", b"")
        if isinstance(body, str):
            body_bytes = body.encode("utf-8", errors="replace")
        else:
            body_bytes = bytes(body or b"")
        if len(body_bytes) > max_bytes:
            raise ValueError(f"HTML response exceeds configured max_html_bytes ({len(body_bytes)} > {max_bytes}).")
        encoding = getattr(response, "encoding", None) or "utf-8"
        try:
            html = body_bytes.decode(encoding, errors="replace")
        except LookupError:
            html = body_bytes.decode("utf-8", errors="replace")
        return body_bytes, html

    @staticmethod
    def _content_type(response: Any) -> str:
        headers = getattr(response, "headers", {}) or {}
        for key, value in headers.items():
            if str(key).lower() == "content-type":
                return str(value).split(";")[0].strip().lower()
        return ""

    @staticmethod
    def _anchor_text_for_links(inventory: dict[str, Any], limit: int) -> list[dict[str, str]]:
        # HTMLParser records link URL and rel. CSS selector extraction below enriches
        # a subset with readable anchor labels if Scrapling returns them.
        return inventory.get("links", [])[:limit]

    def _enrich_links_with_scrapling(self, response: Any, links: list[dict[str, str]]) -> None:
        try:
            href_to_text: dict[str, str] = {}
            for element in response.css("a"):
                href = element.attrib.get("href", "")
                text = " ".join((getattr(element, "text", "") or "").split())[:300]
                if href and text:
                    href_to_text[href] = text
            for link in links:
                raw = link.get("url", "")
                path = urllib.parse.urlsplit(raw)
                link["text"] = link.get("text") or href_to_text.get(path.path, "") or href_to_text.get(raw, "")
        except Exception as exc:
            self.logger.debug("Optional link-label enrichment skipped: %s", exc)

    def _save_raw_html(self, url: str, body: bytes) -> str:
        if not self.config["output"].get("save_raw_html", True):
            return ""
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        path = self.run_dir / "raw_html" / f"{digest}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return str(path.relative_to(self.run_dir)).replace("\\", "/")

    def _download_asset(self, page_url: str, asset: dict[str, str], page_index: int) -> dict[str, Any]:
        url = asset.get("url", "")
        parsed = urllib.parse.urlsplit(url)
        ext = Path(parsed.path).suffix.lower()
        allowed_exts = {x.lower() for x in self.asset_cfg.get("allowed_extensions", [])}
        result = {"page_url": page_url, "url": url, "alt": asset.get("alt", ""), "status": "manifest_only", "local_path": ""}
        if not self.asset_cfg.get("download_assets", False):
            self.db.save_asset(page_url, url, result["alt"], "", "manifest_only")
            return result
        if parsed.hostname not in {d.lower() for d in self.target.get("allowed_domains", [])}:
            result["status"] = "skipped_external_domain"
            self.db.save_asset(page_url, url, result["alt"], "", result["status"])
            return result
        if ext not in allowed_exts:
            result["status"] = "skipped_extension"
            self.db.save_asset(page_url, url, result["alt"], "", result["status"])
            return result
        max_total = int(self.asset_cfg.get("max_assets_total", 30))
        if self.saved_asset_count >= max_total:
            result["status"] = "skipped_total_limit"
            self.db.save_asset(page_url, url, result["alt"], "", result["status"])
            return result
        if not self.policy.allowed(url):
            result["status"] = "blocked_by_robots"
            self.db.save_asset(page_url, url, result["alt"], "", result["status"])
            return result

        max_bytes = int(self.asset_cfg.get("max_bytes_each", 2_000_000))
        request = urllib.request.Request(url, headers={"User-Agent": self.config["project"]["user_agent"]})
        try:
            # Asset downloads are opt-in, same-domain only, size-limited and robots-aware.
            min_delay = self.policy.minimum_delay(url)
            elapsed = time.monotonic() - self.last_request_at
            if elapsed < min_delay:
                time.sleep(min_delay - elapsed)
            self.last_request_at = time.monotonic()
            with urllib.request.urlopen(request, timeout=int(self.crawl.get("timeout_seconds", 45))) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    raise ValueError(f"Not an image content type: {content_type}")
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise ValueError(f"Asset exceeds max_bytes_each ({length} > {max_bytes})")
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError(f"Asset exceeds max_bytes_each ({len(data)} > {max_bytes})")
            digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            local = self.run_dir / "assets" / f"{digest}{ext}"
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            result.update({"status": "downloaded", "local_path": str(local.relative_to(self.run_dir)).replace("\\", "/"), "content_type": content_type, "bytes": len(data)})
            self.saved_asset_count += 1
        except Exception as exc:
            result["status"] = f"download_error: {exc}"[:250]
            self.logger.warning("Asset skipped (%s): %s", url, exc)
        self.db.save_asset(page_url, url, result["alt"], result["local_path"], result["status"])
        return result

    def crawl_site(self) -> dict[str, Any]:
        queue: deque[tuple[str, int]] = deque()
        for seed in self.target.get("start_urls", []):
            normalized = self._normalise_url(seed)
            if normalized:
                queue.append((normalized, 0))
            else:
                self.logger.warning("Ignoring seed outside allowed scope: %s", seed)

        max_pages = int(self.crawl.get("max_pages", 25))
        max_depth = int(self.crawl.get("max_depth", 2))
        max_links = int(self.crawl.get("max_links_per_page", 250))
        max_assets_per_page = int(self.asset_cfg.get("max_assets_per_page", 8))
        errors: list[dict[str, str]] = []
        stop_reason = "completed"

        try:
            while queue and len(self.visited) < max_pages:
                url, depth = queue.popleft()
                if url in self.visited:
                    continue
                self.visited.add(url)
                if not self.policy.allowed(url):
                    message = "Disallowed by robots.txt or robots policy unavailable"
                    self.logger.info("Skipping %s (%s)", url, message)
                    errors.append({"url": url, "error": message})
                    self.db.save_error(url, message)
                    continue

                self.logger.info("Fetching (%s/%s, depth=%s): %s", len(self.visited), max_pages, depth, url)
                try:
                    response = self._request(url)
                    status = int(getattr(response, "status", 0) or 0)
                    final_url = str(getattr(response, "url", url) or url)
                    if status in {403, 429} and self.crawl.get("stop_on_forbidden_or_rate_limit", True):
                        raise CrawlStopped(f"Server returned HTTP {status}; stopping to avoid overloading or circumventing access controls.")
                    # A redirect must remain inside the configured scope too.
                    if not self._normalise_url(final_url):
                        raise CrawlStopped(f"Redirect left the configured domain/path scope; refusing to archive {final_url}")
                    body, html = self._safe_html(response, int(self.crawl.get("max_html_bytes", 5_000_000)))
                    content_type = self._content_type(response)
                    if content_type and "html" not in content_type and "xhtml" not in content_type:
                        self.logger.info("Not an HTML page (%s); not adding to page archive: %s", content_type, url)
                        continue
                    inventory = extract_inventory(html, final_url, int(self.crawl.get("max_text_chars", 24000)))
                    links = self._anchor_text_for_links(inventory, max_links)
                    self._enrich_links_with_scrapling(response, links)
                    raw_path = self._save_raw_html(url, body)
                    now = datetime.now(timezone.utc).isoformat()
                    record: dict[str, Any] = {
                        "url": url,
                        "final_url": final_url,
                        "status": status,
                        "content_type": content_type,
                        "fetched_at": now,
                        "depth": depth,
                        "title": inventory.get("title", ""),
                        "description": inventory.get("description", ""),
                        "canonical_url": inventory.get("canonical_url", ""),
                        "headings": inventory.get("headings", []),
                        "text_excerpt": inventory.get("text_excerpt", ""),
                        "links": links,
                        "images": inventory.get("images", []),
                        "script_sources": inventory.get("script_sources", []),
                        "stylesheets": inventory.get("stylesheets", []),
                        "json_ld_raw": inventory.get("json_ld_raw", []),
                        "interface_labels": inventory.get("interface_labels", []),
                        "raw_html_path": raw_path,
                    }
                    self.pages.append(record)
                    self.db.save_page(record)
                    self.db.save_links(url, links)
                    jsonl_append(self.run_dir / "pages.jsonl", record)
                    self.logger.info("Saved: %s | title=%s | links=%s", url, record["title"][:90], len(links))

                    for asset in inventory.get("images", [])[:max_assets_per_page]:
                        self.all_assets.append(self._download_asset(url, asset, len(self.pages)))

                    for link in links:
                        normalized = self._normalise_url(link.get("url", ""))
                        if normalized and normalized not in self.visited and depth < max_depth:
                            queue.append((normalized, depth + 1))
                        self.all_links.append({"source_url": url, **link})

                except CrawlStopped as exc:
                    stop_reason = str(exc)
                    self.logger.error(stop_reason)
                    errors.append({"url": url, "error": stop_reason})
                    self.db.save_error(url, stop_reason)
                    break
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"
                    self.logger.exception("Failed to fetch %s", url)
                    errors.append({"url": url, "error": message})
                    self.db.save_error(url, message)
        finally:
            self.db.close()

        result = {
            "project": self.config["project"].get("name", "Scrapling crawl"),
            "started_at": self.run_dir.name,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "target_domains": self.target.get("allowed_domains", []),
            "fetch_mode": self.crawl.get("fetch_mode", "dynamic"),
            "pages_saved": len(self.pages),
            "urls_visited": len(self.visited),
            "errors_count": len(errors),
            "stop_reason": stop_reason,
            "pages": self.pages,
            "links": self.all_links,
            "assets": self.all_assets,
            "errors": errors,
            "disclaimer": "This is a page-structure inventory, not a full application clone. Respect the website's terms, copyright, robots.txt, and access limits. Do not redistribute proprietary content or assets without permission.",
        }
        json_dump(self.run_dir / "pages.json", self.pages)
        json_dump(self.run_dir / "links.json", self.all_links)
        json_dump(self.run_dir / "assets_manifest.json", self.all_assets)
        json_dump(self.run_dir / "crawl_errors.json", errors)
        json_dump(self.run_dir / "crawl_summary.json", {k: v for k, v in result.items() if k not in {"pages", "links", "assets", "errors"}})
        return result
