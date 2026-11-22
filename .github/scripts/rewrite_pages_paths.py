#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

SITE_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/openrockets-pages").resolve()
PREFIX = (sys.argv[2] if len(sys.argv) > 2 else "/openrockets.com").rstrip("/")

if not SITE_DIR.is_dir():
    raise SystemExit(f"Site directory does not exist: {SITE_DIR}")

def project_path(raw: str) -> str:
    if not raw.startswith("/") or raw.startswith("//"):
        return raw
    if raw == PREFIX or raw.startswith(PREFIX + "/"):
        return raw
    return PREFIX + raw

ATTR_RE = re.compile(
    r'(?P<prefix>\b(?:src|href|poster|action|data-src|data-lazy-src|data-original)\s*=\s*["\'])'
    r'(?P<url>[^"\']*)'
    r'(?P<suffix>["\'])',
    re.I,
)

SRCSET_RE = re.compile(
    r'(?P<prefix>\b(?:srcset|data-srcset)\s*=\s*["\'])'
    r'(?P<value>[^"\']*)'
    r'(?P<suffix>["\'])',
    re.I,
)

CSS_URL_RE = re.compile(
    r'url\(\s*(?P<quote>["\']?)(?P<url>[^)"\']+)(?P=quote)\s*\)',
    re.I,
)

def rewrite_html(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    def attr_repl(m):
        raw = m.group("url")
        if raw.startswith("/") and not raw.startswith("//"):
            raw = project_path(raw)
        return m.group("prefix") + raw + m.group("suffix")

    text = ATTR_RE.sub(attr_repl, text)

    def srcset_repl(m):
        items = []
        for item in m.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split()
            url = parts[0]
            if url.startswith("/") and not url.startswith("//"):
                url = project_path(url)
            items.append(" ".join([url] + parts[1:]))
        return m.group("prefix") + ", ".join(items) + m.group("suffix")

    text = SRCSET_RE.sub(srcset_repl, text)

    def css_repl(m):
        raw = m.group("url")
        q = m.group("quote")
        if raw.startswith("/") and not raw.startswith("//"):
            raw = project_path(raw)
            return f"url({q}{raw}{q})"
        return m.group(0)

    text = CSS_URL_RE.sub(css_repl, text)

    if text != original:
        path.write_text(text, encoding="utf-8")
        return 1
    return 0

def rewrite_css(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    def css_repl(m):
        raw = m.group("url")
        q = m.group("quote")
        if raw.startswith("/") and not raw.startswith("//"):
            raw = project_path(raw)
            return f"url({q}{raw}{q})"
        return m.group(0)

    text = CSS_URL_RE.sub(css_repl, text)

    if text != original:
        path.write_text(text, encoding="utf-8")
        return 1
    return 0

html_scanned = 0
html_changed = 0
css_scanned = 0
css_changed = 0

for p in SITE_DIR.rglob("*.html"):
    html_scanned += 1
    html_changed += rewrite_html(p)

for p in SITE_DIR.rglob("*.css"):
    css_scanned += 1
    css_changed += rewrite_css(p)

print(json.dumps({
    "site_dir": str(SITE_DIR),
    "prefix": PREFIX,
    "html_scanned": html_scanned,
    "html_changed": html_changed,
    "css_scanned": css_scanned,
    "css_changed": css_changed,
    "external_urls_rewritten": 0,
    "vendor_localization": False
}, indent=2))
