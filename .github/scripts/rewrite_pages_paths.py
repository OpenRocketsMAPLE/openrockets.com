#!/usr/bin/env python3
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

SITE_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/openrockets-pages").resolve()
PREFIX = (sys.argv[2] if len(sys.argv) > 2 else "/openrockets.com").rstrip("/")
REPO_ROOT = Path.cwd()
AUDIT = REPO_ROOT / ".github" / "recovery-audit" / "live-fidelity-sync.json"

STATIC_SUFFIXES = {
    ".css", ".js", ".mjs", ".cjs", ".json", ".xml", ".txt", ".map",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".mov", ".pdf",
}

if not SITE_DIR.is_dir():
    raise SystemExit(f"Site directory does not exist: {SITE_DIR}")

external_map = {}
if AUDIT.is_file():
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    external_map = data.get("external_archive_map", {}) or {}

reverse_external = {Path(v).as_posix(): k for k, v in external_map.items()}

def project_path(path: str) -> str:
    if not path.startswith("/") or path.startswith("//"):
        return path
    if path == PREFIX or path.startswith(PREFIX + "/"):
        return path
    return PREFIX + path

def mapped_external(raw: str):
    candidate = html.unescape(raw.strip())
    rel = external_map.get(candidate)
    if not rel:
        return None
    suffix = Path(urlparse(candidate).path).suffix.lower() or Path(rel).suffix.lower()
    if suffix not in STATIC_SUFFIXES:
        return None
    return f"{PREFIX}/{Path(rel).as_posix()}"

def rewrite_basic_url(raw: str) -> str:
    stripped = raw.strip()
    if not stripped or stripped.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:")):
        return raw
    if stripped.startswith("/") and not stripped.startswith("//"):
        return project_path(stripped)
    return raw

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
MEDIA_TAG_RE = re.compile(r'<(?:img|source|video|audio|link)\b[^>]*>', re.I)
CSS_URL_RE = re.compile(r'url\(\s*(?P<quote>["\']?)(?P<url>[^)"\']+)(?P=quote)\s*\)', re.I)

def rewrite_tag_external_assets(tag_text: str) -> str:
    def repl(m):
        raw = m.group("url")
        mapped = mapped_external(raw)
        if mapped:
            return m.group("prefix") + mapped + m.group("suffix")
        return m.group(0)
    return ATTR_RE.sub(repl, tag_text)

def rewrite_html(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")

    # First, make every site-root URL work under the GitHub Pages project prefix.
    def attr_repl(m):
        raw = m.group("url")
        rewritten = rewrite_basic_url(raw)
        return m.group("prefix") + rewritten + m.group("suffix")

    text = ATTR_RE.sub(attr_repl, text)

    def srcset_repl(m):
        items = []
        for item in m.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split()
            url = parts[0]
            mapped = mapped_external(url)
            rewritten = mapped or rewrite_basic_url(url)
            items.append(" ".join([rewritten] + parts[1:]))
        return m.group("prefix") + ", ".join(items) + m.group("suffix")

    text = SRCSET_RE.sub(srcset_repl, text)

    # Localize archived visual/style assets, but deliberately leave third-party
    # runtime <script> elements remote because many depend on their own origin.
    text = MEDIA_TAG_RE.sub(lambda m: rewrite_tag_external_assets(m.group(0)), text)

    # Root-relative URLs inside inline CSS need the project prefix too.
    def inline_css_repl(m):
        raw = html.unescape(m.group("url").strip())
        q = m.group("quote")

        mapped = mapped_external(raw)
        if mapped:
            return f"url({q}{mapped}{q})"

        if raw.startswith("/") and not raw.startswith("//"):
            rewritten = project_path(raw)
            return f"url({q}{rewritten}{q})"

        return m.group(0)

    text = CSS_URL_RE.sub(inline_css_repl, text)
    path.write_text(text, encoding="utf-8")

def rewrite_css(path: Path):
    rel = path.relative_to(SITE_DIR).as_posix()
    source_url = reverse_external.get(rel)
    if source_url is None:
        source_url = "https://openrockets.com/" + rel

    text = path.read_text(encoding="utf-8", errors="ignore")

    def css_repl(m):
        raw = html.unescape(m.group("url").strip())
        if not raw or raw.startswith(("data:", "blob:", "#")):
            return m.group(0)

        q = m.group("quote")
        parsed_source = urlparse(source_url)
        absolute = urljoin(source_url, raw)
        mapped = external_map.get(absolute)

        if mapped:
            rewritten = f"{PREFIX}/{Path(mapped).as_posix()}"
            return f"url({q}{rewritten}{q})"

        parsed = urlparse(absolute)

        # CSS originally hosted on openrockets.com: root URLs must receive
        # the GitHub Pages project prefix.
        if (parsed.hostname or "").lower() == "openrockets.com":
            if raw.startswith("/"):
                rewritten = project_path(raw)
                return f"url({q}{rewritten}{q})"
            return m.group(0)

        # CSS archived from another origin: if a relative/root dependency was
        # not captured, keep it on its original host rather than accidentally
        # requesting it from the GitHub Pages origin.
        if rel in reverse_external and not urlparse(raw).scheme and not raw.startswith("//"):
            return f"url({q}{absolute}{q})"

        return m.group(0)

    text = CSS_URL_RE.sub(css_repl, text)
    path.write_text(text, encoding="utf-8")

html_count = 0
css_count = 0
for p in SITE_DIR.rglob("*.html"):
    rewrite_html(p)
    html_count += 1

for p in SITE_DIR.rglob("*.css"):
    rewrite_css(p)
    css_count += 1

print(json.dumps({
    "site_dir": str(SITE_DIR),
    "prefix": PREFIX,
    "html_files_rewritten": html_count,
    "css_files_rewritten": css_count,
    "external_archive_entries": len(external_map),
}, indent=2))
