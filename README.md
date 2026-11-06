# Owlbear Toolkit — Scrapling Cloud Crawler v1.0

A conservative, configurable crawler starter project. It uses [Scrapling](https://github.com/D4Vinci/Scrapling) to fetch public HTML pages, including JavaScript-rendered pages, and creates a structured research archive for a future Owlbear Rodeo extension.

> **Important:** this is a page/DOM inventory crawler, not a website copier or a complete app reverse-engineering tool. It does not log in, submit forms, bypass bot challenges, capture private account data, or reproduce the website's backend logic. Use it only where permitted. Do not redistribute proprietary code, text, images, or licensed game-book content without permission.

## Included

- Scrapling fetch modes: `http` and `dynamic` (Chromium / JavaScript rendering).
- Scrapling is constrained to `>=0.4.15,<0.5` because v0.5 removed the plain `DynamicFetcher` and replaced it with the stealthy browser backend. This package deliberately uses the pre-v0.5 plain browser backend and does not enable anti-bot solving or fingerprint-evasion features.
- GitHub Actions cloud workflow (`workflow_dispatch`; run manually).
- Same-domain allowlist and URL scope controls.
- `robots.txt` checks; fail-closed behavior when robots policy cannot be read.
- Conservative defaults: 25 pages, depth 2, 3-second delay, serial fetches.
- JSON, JSONL, SQLite, raw HTML snapshots, asset manifest, logs, and a ZIP archive.
- Optional same-domain image downloads (off by default, extension/MIME/size limited).
- Windows setup and run instructions in `docs/WINDOWS.md`.

## Quick start: GitHub Actions cloud

1. Extract this ZIP on your computer.
2. Create a **private** GitHub repository, for example `owlbear-toolkit-scrapling`.
3. Push the contents of this folder to the repository root using GitHub Desktop or Git. Make sure the hidden `.github/workflows/scrape.yml` file is included.
4. Open the repository's **Actions** tab.
5. Choose **Scrapling cloud crawl** → **Run workflow**.
6. Start with the defaults (`25` pages, depth `2`, dynamic mode, 3-second delay, assets off).
7. When the run finishes, open the run and download the artifact named `owlbear-toolkit-scrapling-N`.
8. Inside the artifact, find `exports/*_scrape_bundle.zip`. This is the portable research archive.

The workflow installs Scrapling and, for dynamic mode, its browser dependencies. GitHub Actions is the execution host; the crawl does not run inside the ChatGPT Python environment.

## Configure the target

Edit `config/settings.json` before uploading or rerunning:

- `target.start_urls`: initial pages. The play5e preset seeds the home page, DM Table, character guide, classes, spells, monsters, magic items, rules, tools, conditions, equipment, species, supported books, and FAQ.
- `target.allowed_domains`: exact domains the crawler may visit.
- `target.path_prefixes`: allowed URL paths. `"/"` means all paths on the allowed domain.
- `target.exclude_path_prefixes`: paths to skip (accounts/login/logout are excluded by default).
- `target.obey_robots_txt`: keep `true` unless you have explicit authorization and a valid reason to change it.
- `crawl.fetch_mode`: `dynamic` for JavaScript-driven pages; `http` for ordinary HTML.
- `crawl.max_pages`, `max_depth`, `delay_seconds`: crawl limits.
- `assets.download_assets`: `false` by default. Enable only when asset downloading is permitted. Only listed extensions, same-domain URLs, image MIME types, size limits and robots rules are honored.

Do not add a login cookie, password, API key, or session token to the repository. This scaffold is intended for public pages only.

## Output layout

Each run creates a timestamped folder under `output/`:

```text
output/<UTC-run-id>/
├── REPORT.md
├── effective_settings.json
├── crawl_summary.json
├── pages.json
├── pages.jsonl
├── links.json
├── assets_manifest.json
├── crawl_errors.json
├── archive.sqlite3
├── raw_html/
└── assets/                 # only if explicitly enabled and permitted
```

A ZIP archive is also created under `exports/`. Logs are written under `logs/`.

### SQLite tables

- `pages`: page metadata, extracted text excerpt, and HTML path.
- `links`: source/target URL and anchor label.
- `assets`: image reference and optional local file path.
- `crawl_errors`: URL, timestamp, and error.

## What the extraction collects

For each permitted HTML page, the crawler inventories title, description, canonical URL, headings, text excerpt, links, image references, external script/stylesheet URLs, JSON-LD raw blocks, and basic interface labels. It also saves the response HTML when enabled.

This is intentionally not a full clone. JavaScript-driven features can load data through API requests after the first page render; this v1.0 scaffold inventories the visible DOM and resource references but does not automatically reconstruct private APIs or app state. Those sources should be reviewed manually and used only when publicly accessible and permitted by the site owner/licence.

## Local commands (optional)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
scrapling install
python run_scrape.py
```

`docs/WINDOWS.md` contains more detailed Windows steps. You can omit `scrapling install` when using `--fetch-mode http` only.

## Tests

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

## Responsible use

- Check the target site's current terms, copyright/licences, and robots.txt before every crawl.
- Use a private repository for research output.
- Do not redistribute proprietary text, images, source code, or paid/licensed content.
- Start small. Stop if the site returns `403` or `429`; this crawler deliberately does not try to bypass blocks.
- Do not use this tool to collect personal data or authenticated content.

## References

- Scrapling: <https://github.com/D4Vinci/Scrapling>
- Scrapling documentation: <https://scrapling.readthedocs.io/en/latest/>
- GitHub Actions: <https://docs.github.com/actions>
