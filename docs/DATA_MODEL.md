# Data model for the next Owlbear extension phase

The crawler's output is a discovery archive rather than a ready-made game database.

Suggested mapping into later modules:

| Archive field | Possible next use |
|---|---|
| `title`, `description`, `headings` | Feature and page inventory |
| `text_excerpt`, `raw_html_path` | Manual UI/DOM review |
| `links` | Public route map |
| `script_sources`, `stylesheets` | Resource inventory (references only) |
| `json_ld_raw` | Structured public metadata, if present |
| `assets_manifest.json` | Asset provenance and permission review |
| `archive.sqlite3` | Searchable local research archive |

For D&D rules and stat data in the final extension, prefer SRD content or original/homebrew data with appropriate attribution and licensing. Do not transform this crawl archive into a public redistribution of another site's proprietary content.
