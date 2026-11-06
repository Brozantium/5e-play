from scraper.extract import extract_inventory


def test_extracts_page_inventory():
    html = '''<!doctype html>
    <html><head>
      <title>Test Page</title>
      <meta name="description" content="A short description">
      <link rel="canonical" href="https://example.org/canonical">
      <script type="application/ld+json">{"@type":"Thing"}</script>
    </head><body>
      <h1>Heading One</h1><p>Hello world</p>
      <a href="/about">About</a>
      <img src="/image.png" alt="Example image">
      <script src="/app.js"></script>
      <link rel="stylesheet" href="/style.css">
    </body></html>'''
    result = extract_inventory(html, "https://example.org/", 1000)
    assert result["title"] == "Test Page"
    assert result["description"] == "A short description"
    assert result["canonical_url"] == "https://example.org/canonical"
    assert result["headings"][0]["text"] == "Heading One"
    assert result["links"][0]["url"] == "https://example.org/about"
    assert result["images"][0]["url"] == "https://example.org/image.png"
    assert "https://example.org/app.js" in result["script_sources"]
    assert "https://example.org/style.css" in result["stylesheets"]
    assert result["json_ld_raw"][0] == '{"@type":"Thing"}'


def test_ignores_non_http_links():
    html = '<html><body><a href="mailto:person@example.org">Mail</a><a href="javascript:void(0)">Click</a></body></html>'
    result = extract_inventory(html, "https://example.org/", 1000)
    assert result["links"] == []
