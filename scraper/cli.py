"""Command-line entry point."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .crawler import ScraplingCrawler
from .storage import create_bundle, json_dump

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    for section in ("project", "target", "crawl", "assets", "output"):
        if section not in config:
            raise ValueError(f"Missing config section: {section}")
    if config["crawl"].get("fetch_mode") not in {"http", "dynamic"}:
        raise ValueError("crawl.fetch_mode must be 'http' or 'dynamic'.")
    if int(config["crawl"].get("max_pages", 0)) < 1:
        raise ValueError("crawl.max_pages must be at least 1.")
    if not config["target"].get("allowed_domains"):
        raise ValueError("target.allowed_domains must contain at least one domain.")
    return config


def setup_logging(log_path: Path, level: str = "INFO") -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("owlbear_scrapling")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def write_report(path: Path, result: dict[str, Any], bundle_path: Path | None = None) -> None:
    lines = [
        "# Scrapling Cloud Crawl Report",
        "",
        f"- Project: {result.get('project')}",
        f"- Started: {result.get('started_at')}",
        f"- Finished: {result.get('finished_at')}",
        f"- Fetch mode: {result.get('fetch_mode')}",
        f"- Pages saved: {result.get('pages_saved')}",
        f"- URLs visited: {result.get('urls_visited')}",
        f"- Errors: {result.get('errors_count')}",
        f"- Stop reason: {result.get('stop_reason')}",
        "",
        "## Page inventory",
        "",
    ]
    for page in result.get("pages", []):
        lines.append(f"- [{page.get('title') or '(untitled)'}]({page.get('url')}) — HTTP {page.get('status')}; depth {page.get('depth')}")
    lines += [
        "",
        "## Output files",
        "",
        "- `archive.sqlite3`: searchable local archive database.",
        "- `pages.json` / `pages.jsonl`: extracted page records.",
        "- `links.json`: discovered same-site and external link inventory.",
        "- `assets_manifest.json`: image references and optional saved asset paths.",
        "- `raw_html/`: response HTML snapshots, if enabled.",
        "- `assets/`: opt-in, same-domain image downloads only.",
        "",
        "## Important limitations",
        "",
        "- This is a structural inventory, not a complete reconstruction of the source website.",
        "- JavaScript interactions, authenticated content, browser storage, and backend business logic are not cloned.",
        "- A page may expose only a shell in its HTML; inspect its public links and permitted data sources separately.",
        "- Do not redistribute proprietary source code, text, images, or licensed book content without permission.",
    ]
    if bundle_path:
        lines += ["", f"- Bundle: `{bundle_path.name}`"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a conservative Scrapling website inventory crawl.")
    parser.add_argument("--config", default="config/settings.json", help="Path to JSON settings file.")
    parser.add_argument("--max-pages", type=int, help="Override maximum pages for this run.")
    parser.add_argument("--max-depth", type=int, help="Override maximum link depth.")
    parser.add_argument("--fetch-mode", choices=["http", "dynamic"], help="Use static HTTP or JavaScript browser mode.")
    parser.add_argument("--delay-seconds", type=float, help="Minimum seconds between requests to the same host.")
    parser.add_argument("--download-assets", choices=["true", "false"], help="Opt-in same-domain image downloads.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    config = load_config(config_path)

    if args.max_pages is not None:
        config["crawl"]["max_pages"] = max(1, args.max_pages)
    if args.max_depth is not None:
        config["crawl"]["max_depth"] = max(0, args.max_depth)
    if args.fetch_mode:
        config["crawl"]["fetch_mode"] = args.fetch_mode
    if args.delay_seconds is not None:
        config["crawl"]["delay_seconds"] = max(1.0, args.delay_seconds)
    if args.download_assets is not None:
        config["assets"]["download_assets"] = args.download_assets == "true"

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_dir = Path(config["output"].get("base_dir", "output"))
    exports_dir = Path(config["output"].get("exports_dir", "exports"))
    logs_dir = Path(config["output"].get("logs_dir", "logs"))
    if not base_dir.is_absolute():
        base_dir = PROJECT_ROOT / base_dir
    if not exports_dir.is_absolute():
        exports_dir = PROJECT_ROOT / exports_dir
    if not logs_dir.is_absolute():
        logs_dir = PROJECT_ROOT / logs_dir

    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(logs_dir / f"{run_id}.log")
    json_dump(run_dir / "effective_settings.json", config)
    logger.info("Starting %s", config["project"].get("name", "Scrapling crawl"))
    logger.info("Mode=%s | max_pages=%s | max_depth=%s", config["crawl"]["fetch_mode"], config["crawl"]["max_pages"], config["crawl"]["max_depth"])

    try:
        crawler = ScraplingCrawler(config, run_dir, logger)
        result = crawler.crawl_site()
        report_path = run_dir / "REPORT.md"
        write_report(report_path, result)
        bundle_path = create_bundle(run_dir, exports_dir, run_id)
        write_report(report_path, result, bundle_path)
        logger.info("Finished. Pages saved=%s; errors=%s", result["pages_saved"], result["errors_count"])
        logger.info("ZIP bundle: %s", bundle_path)
        print(f"\nSCRAPE_BUNDLE={bundle_path}")
        return 0
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception:
        logger.exception("Crawler failed before completing the run.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
