# Windows 10/11 — setup and run

## 1. Install prerequisites

1. Install Python 3.11 from <https://www.python.org/downloads/windows/>.
2. During setup, tick **Add Python to PATH**.
3. Install Git for Windows if you plan to push the project to GitHub: <https://git-scm.com/download/win>.
4. Extract `OwlbearToolkitScraplingCloud.zip` to a folder, for example `C:\Projects\owlbear-toolkit-scrapling-cloud`.

## 2. Open PowerShell in the project folder

In File Explorer, open the project folder, click the address bar, type `powershell`, and press Enter.

## 3. Create a virtual environment

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

If PowerShell blocks activation, use this for the current PowerShell process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 4. Install Chromium support for JavaScript pages

```powershell
scrapling install
```

This step is needed for `dynamic` mode. The project pins Scrapling to the 0.4.x series to retain its standard Playwright `DynamicFetcher` (the v0.5 browser backend changed to a stealthy implementation). This project does not enable challenge solving or anti-bot bypass. The current target is JavaScript-driven, so dynamic mode is the default. For a quick static-only check, you can skip this step and run with `--fetch-mode http`.

## 5. Review configuration before crawling

Open `config\settings.json` in Notepad or VS Code. Check seed URLs, allowed domains, `max_pages`, `max_depth`, delay, and `obey_robots_txt`. Leave asset downloads off unless you have permission to download and reuse them.

## 6. Run the crawler

```powershell
python run_scrape.py
```

Or override options for one run:

```powershell
python run_scrape.py --max-pages 10 --max-depth 1 --fetch-mode dynamic --delay-seconds 4 --download-assets false
```

## 7. Find your files

- `output\<run-id>\`: JSON, SQLite, raw HTML, manifest, report.
- `exports\<run-id>_scrape_bundle.zip`: one ZIP containing the full run archive.
- `logs\<run-id>.log`: detailed log.

## Troubleshooting

- `ModuleNotFoundError: scrapling`: activate `.venv` and rerun `python -m pip install -e .`.
- Browser executable missing: rerun `scrapling install` after the project dependencies are installed.
- PowerShell says scripts are disabled: use the process-only execution policy command above.
- HTTP 403/429: the run stops by design. Do not switch to stealth/proxy or try to defeat the restriction. Check terms/robots and seek permission.
- No pages saved: verify `robots.txt`, network access, exact allowed domain names, and seed URLs. Use `--fetch-mode http` once to compare with `dynamic` mode.
