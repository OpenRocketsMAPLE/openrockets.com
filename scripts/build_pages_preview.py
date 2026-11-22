#!/usr/bin/env python3
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

REPO_NAME = "openrockets.com"
BASE_PATH = f"/{REPO_NAME}"

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "recovery_snapshot"
PAGES = SNAPSHOT / "pages"
ASSETS = SNAPSHOT / "assets"
MAP_FILE = SNAPSHOT / "metadata" / "url_to_saved_file.json"
OUT = ROOT / "_site"

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

shutil.copytree(PAGES, OUT, dirs_exist_ok=True)
if ASSETS.exists():
    shutil.copytree(ASSETS, OUT / "_assets", dirs_exist_ok=True)

(OUT / ".nojekyll").write_text("", encoding="utf-8")

mapping = json.loads(MAP_FILE.read_text(encoding="utf-8"))
inverse_pages = {
    saved: url
    for url, saved in mapping.items()
    if isinstance(saved, str) and saved.startswith("pages/")
}

def target_for_saved(saved: str):
    if saved.startswith("pages/"):
        rel = saved[len("pages/"):]
        if rel == "index.html":
            return BASE_PATH + "/"
        if rel.endswith("/index.html"):
            return BASE_PATH + "/" + rel[:-len("index.html")]
        return BASE_PATH + "/" + rel
    if saved.startswith("assets/"):
        return BASE_PATH + "/_assets/" + saved[len("assets/"):]
    if saved.startswith("source_maps/"):
        return BASE_PATH + "/_source_maps/" + saved[len("source_maps/"):]
    return None

def rewrite_url(value: str, page_url: str):
    raw = value.strip()
    if not raw or raw.startswith(("#", "data:", "blob:", "mailto:", "tel:", "javascript:")):
        return value

    absolute = urljoin(page_url, raw)

    if absolute in mapping:
        target = target_for_saved(mapping[absolute])
        if target:
            return target

    parsed = urlparse(absolute)
    if parsed.hostname == "openrockets.com":
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        fragment = f"#{parsed.fragment}" if parsed.fragment else ""
        return BASE_PATH + path + query + fragment

    return value

attr_re = re.compile(r'(?P<prefix>\b(?:href|src|poster|action)\s*=\s*["\'])(?P<url>[^"\']*)(?P<suffix>["\'])', re.I)
srcset_re = re.compile(r'(?P<prefix>\bsrcset\s*=\s*["\'])(?P<value>[^"\']*)(?P<suffix>["\'])', re.I)
css_url_re = re.compile(r'url\(\s*(?P<quote>["\']?)(?P<url>[^)"\']+)(?P=quote)\s*\)', re.I)

for html_file in OUT.rglob("*.html"):
    rel = html_file.relative_to(OUT).as_posix()
    saved_key = "pages/" + rel
    page_url = inverse_pages.get(saved_key)

    if not page_url:
        if rel == "index.html":
            page_url = "https://openrockets.com/"
        elif rel.endswith("/index.html"):
            page_url = "https://openrockets.com/" + rel[:-len("index.html")]
        else:
            page_url = "https://openrockets.com/" + rel

    text = html_file.read_text(encoding="utf-8", errors="ignore")

    def attr_sub(match):
        return (
            match.group("prefix")
            + rewrite_url(match.group("url"), page_url)
            + match.group("suffix")
        )

    def srcset_sub(match):
        pieces = []
        for item in match.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            parts = item.split()
            rewritten = rewrite_url(parts[0], page_url)
            pieces.append(" ".join([rewritten] + parts[1:]))
        return match.group("prefix") + ", ".join(pieces) + match.group("suffix")

    def css_sub(match):
        rewritten = rewrite_url(match.group("url"), page_url)
        quote = match.group("quote")
        return f"url({quote}{rewritten}{quote})"

    text = attr_re.sub(attr_sub, text)
    text = srcset_re.sub(srcset_sub, text)
    text = css_url_re.sub(css_sub, text)

    html_file.write_text(text, encoding="utf-8")

# Copy source maps for inspection, though they are not required to render.
source_maps = SNAPSHOT / "source_maps"
if source_maps.exists():
    shutil.copytree(source_maps, OUT / "_source_maps", dirs_exist_ok=True)

# Helpful preview marker.
(OUT / "RECOVERY_PREVIEW.txt").write_text(
    "GitHub Pages preview generated from the verified OpenRockets public-site recovery snapshot.\n",
    encoding="utf-8",
)

print(f"Built Pages preview at {OUT}")
