import json
from pathlib import Path

from scraper.cli import load_config


def test_default_config_is_valid():
    config = load_config(Path("config/settings.json"))
    assert config["crawl"]["fetch_mode"] in {"http", "dynamic"}
    assert "play5e.net" in config["target"]["allowed_domains"]


def test_default_assets_are_opt_in():
    config = json.loads(Path("config/settings.json").read_text(encoding="utf-8"))
    assert config["assets"]["download_assets"] is False


def test_target_scope_is_restricted_to_configured_domain_and_path():
    from scraper.crawler import ScraplingCrawler
    import logging
    import tempfile

    config = load_config(Path("config/settings.json"))
    with tempfile.TemporaryDirectory() as temp_dir:
        crawler = ScraplingCrawler(config, Path(temp_dir), logging.getLogger("test"))
        assert crawler._normalise_url("https://play5e.net/table") == "https://play5e.net/table"
        assert crawler._normalise_url("https://example.com/table") is None
        assert crawler._normalise_url("javascript:alert(1)") is None
        assert crawler._normalise_url("https://play5e.net/login") is None
        crawler.db.close()


def test_crawler_writes_archive_outputs_without_network(tmp_path):
    import logging
    from scraper.crawler import ScraplingCrawler

    config = load_config(Path("config/settings.json"))
    config["target"]["obey_robots_txt"] = False
    config["target"]["start_urls"] = ["https://play5e.net/table"]
    config["crawl"]["max_pages"] = 1
    config["crawl"]["max_depth"] = 0
    config["assets"]["download_assets"] = False

    class FakeResponse:
        status = 200
        url = "https://play5e.net/table"
        encoding = "utf-8"
        headers = {"content-type": "text/html; charset=utf-8"}
        body = b"<html><head><title>DM Toolkit</title></head><body><h1>Initiative</h1><a href='/monsters'>Monsters</a></body></html>"

        def css(self, selector):
            return []

    crawler = ScraplingCrawler(config, tmp_path / "run", logging.getLogger("test"))
    crawler._request = lambda url: FakeResponse()
    result = crawler.crawl_site()

    assert result["pages_saved"] == 1
    assert (tmp_path / "run" / "pages.json").exists()
    assert (tmp_path / "run" / "pages.jsonl").exists()
    assert (tmp_path / "run" / "archive.sqlite3").exists()
    assert list((tmp_path / "run" / "raw_html").glob("*.html"))
