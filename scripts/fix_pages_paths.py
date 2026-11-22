#!/usr/bin/env python3
import os, posixpath, re, shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_TOP = {".git", ".github", "_vendor", "scripts"}

def route_relative(html_file: Path, raw: str):
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return raw

    parts = urlsplit(raw)
    path = parts.path
    if not path.startswith("/") or path.startswith("//"):
        return raw

    target = path.lstrip("/")
    if not target:
        # Link to site root.
        target = "index.html"

    start_dir = html_file.parent.relative_to(ROOT).as_posix()
    if start_dir == ".":
        start_dir = "."

    rel = posixpath.relpath(target, start=start_dir)
    if path.endswith("/") and not rel.endswith("/"):
        rel += "/"
    if rel == "index.html" and path == "/":
        rel = "./"

    return urlunsplit(("", "", rel, parts.query, parts.fragment))

def css_relative(css_file: Path, raw: str):
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return raw
    parts = urlsplit(raw)
    target = parts.path.lstrip("/")
    if not target:
        return raw
    start_dir = css_file.parent.relative_to(ROOT).as_posix()
    if start_dir == ".":
        start_dir = "."
    rel = posixpath.relpath(target, start=start_dir)
    return urlunsplit(("", "", rel, parts.query, parts.fragment))

# CDN-injected runtime scripts are not website source and break on GitHub Pages.
CLOUDFLARE_SCRIPT_RE = re.compile(
    r'<script\b[^>]*\bsrc=(["\'])(?:https?:)?//static\.cloudflareinsights\.com/beacon\.min\.js[^"\']*\1[^>]*>\s*</script>'
    r'|<script\b[^>]*\bsrc=(["\'])/cdn-cgi/[^"\']*\2[^>]*>\s*</script>'
    r'|<script\b[^>]*\bsrc=(["\'])https?://openrockets\.com/cdn-cgi/[^"\']*\3[^>]*>\s*</script>',
    re.I | re.S,
)

ATTR_RE = re.compile(
    r'(?P<prefix>\b(?:href|src|poster|action|data-src|data-lazy-src|data-original)\s*=\s*(?P<q>["\']))'
    r'(?P<url>/[^"\']*)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

SRCSET_RE = re.compile(
    r'(?P<prefix>\b(?:srcset|data-srcset)\s*=\s*(?P<q>["\']))'
    r'(?P<value>[^"\']*)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

INLINE_CSS_URL_RE = re.compile(
    r'url\(\s*(?P<q>["\']?)(?P<url>/[^)"\']+)(?P=q)\s*\)',
    re.I,
)

changed_html = 0
changed_css = 0
removed_cf_scripts = 0

for html_file in ROOT.rglob("*.html"):
    rel_parts = html_file.relative_to(ROOT).parts
    if rel_parts and rel_parts[0] in EXCLUDE_TOP:
        continue

    text = html_file.read_text(encoding="utf-8", errors="ignore")
    original = text

    text, n = CLOUDFLARE_SCRIPT_RE.subn("", text)
    removed_cf_scripts += n

    def attr_sub(m):
        raw = m.group("url")
        # Root-relative Cloudflare runtime URLs have no static equivalent.
        if raw.startswith("/cdn-cgi/"):
            return m.group(0)
        return m.group("prefix") + route_relative(html_file, raw) + m.group("suffix")

    text = ATTR_RE.sub(attr_sub, text)

    def srcset_sub(m):
        out = []
        for item in m.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            url = bits[0]
            if url.startswith("/") and not url.startswith("//"):
                url = route_relative(html_file, url)
            out.append(" ".join([url] + bits[1:]))
        return m.group("prefix") + ", ".join(out) + m.group("suffix")

    text = SRCSET_RE.sub(srcset_sub, text)

    def inline_css_sub(m):
        url = m.group("url")
        if url.startswith("//"):
            return m.group(0)
        q = m.group("q")
        return f"url({q}{route_relative(html_file, url)}{q})"

    text = INLINE_CSS_URL_RE.sub(inline_css_sub, text)

    # Remove known Cloudflare RUM/challenge references that can occur in injected inline snippets.
    text = re.sub(
        r'<script\b[^>]*>[^<]*(?:cdn-cgi/(?:rum|challenge-platform)|cloudflareinsights)[\s\S]*?</script>',
        "",
        text,
        flags=re.I,
    )

    if text != original:
        html_file.write_text(text, encoding="utf-8")
        changed_html += 1

for css_file in ROOT.rglob("*.css"):
    rel_parts = css_file.relative_to(ROOT).parts
    if rel_parts and rel_parts[0] in EXCLUDE_TOP:
        continue
    text = css_file.read_text(encoding="utf-8", errors="ignore")
    original = text

    def css_sub(m):
        q = m.group("q")
        url = m.group("url")
        return f"url({q}{css_relative(css_file, url)}{q})"

    text = INLINE_CSS_URL_RE.sub(css_sub, text)
    if text != original:
        css_file.write_text(text, encoding="utf-8")
        changed_css += 1

print({
    "changed_html_files": changed_html,
    "changed_css_files": changed_css,
    "removed_cloudflare_script_tags": removed_cf_scripts,
})

# Sanity: homepage must still have functional TermsFeed source initialization and favicon.
index = ROOT / "index.html"
s = index.read_text(encoding="utf-8", errors="ignore")
assert "cookieconsent.run(" in s
assert "www.termsfeed.com/public/cookie-consent" in s
assert "openthread_logo_bash-trans-removebg-preview (1).png" in s
