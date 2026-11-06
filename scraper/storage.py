"""JSON, JSONL, SQLite and ZIP output helpers."""
from __future__ import annotations

import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def json_dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def jsonl_append(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


class ArchiveDB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY,
                final_url TEXT,
                status INTEGER,
                content_type TEXT,
                title TEXT,
                description TEXT,
                canonical_url TEXT,
                depth INTEGER,
                fetched_at TEXT,
                raw_html_path TEXT,
                text_excerpt TEXT,
                record_json TEXT
            );
            CREATE TABLE IF NOT EXISTS links (
                source_url TEXT,
                target_url TEXT,
                anchor_text TEXT,
                rel TEXT,
                PRIMARY KEY (source_url, target_url)
            );
            CREATE TABLE IF NOT EXISTS assets (
                page_url TEXT,
                asset_url TEXT,
                alt_text TEXT,
                local_path TEXT,
                status TEXT,
                PRIMARY KEY (page_url, asset_url)
            );
            CREATE TABLE IF NOT EXISTS crawl_errors (
                url TEXT,
                happened_at TEXT,
                error TEXT
            );
            """
        )
        self.conn.commit()

    def save_page(self, record: dict[str, Any]) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO pages
            (url, final_url, status, content_type, title, description, canonical_url,
             depth, fetched_at, raw_html_path, text_excerpt, record_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("url"), record.get("final_url"), record.get("status"),
                record.get("content_type"), record.get("title"), record.get("description"),
                record.get("canonical_url"), record.get("depth"), record.get("fetched_at"),
                record.get("raw_html_path"), record.get("text_excerpt"),
                json.dumps(record, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def save_links(self, source_url: str, links: Iterable[dict[str, str]]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO links (source_url, target_url, anchor_text, rel) VALUES (?, ?, ?, ?)",
            [(source_url, l.get("url", ""), l.get("text", ""), l.get("rel", "")) for l in links],
        )
        self.conn.commit()

    def save_asset(self, page_url: str, asset_url: str, alt_text: str, local_path: str, status: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO assets (page_url, asset_url, alt_text, local_path, status) VALUES (?, ?, ?, ?, ?)",
            (page_url, asset_url, alt_text, local_path, status),
        )
        self.conn.commit()

    def save_error(self, url: str, error: str) -> None:
        self.conn.execute(
            "INSERT INTO crawl_errors (url, happened_at, error) VALUES (?, ?, ?)",
            (url, datetime.now(timezone.utc).isoformat(), error[:2000]),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()


def create_bundle(run_dir: Path, exports_dir: Path, run_id: str) -> Path:
    exports_dir.mkdir(parents=True, exist_ok=True)
    bundle = exports_dir / f"{run_id}_scrape_bundle.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(run_dir.parent))
    return bundle
