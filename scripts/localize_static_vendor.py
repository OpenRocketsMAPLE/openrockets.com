#!/usr/bin/env python3
import html
import json
import posixpath
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / ".github" / "recovery-audit" / "live-fidelity-sync.json"
data = json.loads(AUDIT.read_text(encoding="utf-8"))
external_map = data.get("external_archive_map", {})
same_map = data.get("same_host_url_map", {})

# Normalize paths from audit.
external_map = {u: p.replace("\\", "/") for u, p in external_map.items()}
same_map = {u: p.replace("\\", "/") for u, p in same_map.items()}
reverse_external = {p: u for u, p in external_map.items()}
reverse_same = {p: u for u, p in same_map.items()}

STATIC_SAFE_EXTS = {
    ".css",".png",".jpg",".jpeg",".webp",".gif",".svg",".ico",".avif",
    ".woff",".woff2",".ttf",".otf",".eot",".json"
}

def rel_from_file(source_file: Path, target_rel: str) -> str:
    start = source_file.parent.relative_to(ROOT).as_posix()
    if start == ".":
        start = "."
    return posixpath.relpath(target_rel, start=start)

def mapped_static(url: str):
    if not url:
        return None
    u = html.unescape(url.strip())
    if u in external_map:
        target = external_map[u]
        if Path(urlparse(u).path).suffix.lower() in STATIC_SAFE_EXTS or Path(target).suffix.lower() in STATIC_SAFE_EXTS:
            return target
    return None

ATTR_RE = re.compile(r'(?P<name>\b(?:href|src|poster)\s*=\s*)(?P<q>["\'])(?P<url>[^"\']+)(?P=q)', re.I)
SRCSET_RE = re.compile(r'(?P<name>\bsrcset\s*=\s*)(?P<q>["\'])(?P<value>[^"\']+)(?P=q)', re.I)
STYLE_ATTR_RE = re.compile(r'(?P<name>\bstyle\s*=\s*)(?P<q>["\'])(?P<value>[^"\']*)(?P=q)', re.I)
CSS_URL_RE = re.compile(r'url\(\s*(?P<q>["\']?)(?P<url>[^)"\']+)(?P=q)\s*\)', re.I)
CSS_IMPORT_RE = re.compile(r'@import\s+(?P<q>["\'])(?P<url>[^"\']+)(?P=q)', re.I)

def rewrite_css_text(text: str, source_file: Path, base_url: str):
    def replace_url(m):
        raw = html.unescape(m.group("url").strip())
        if raw.startswith(("data:","blob:","#")):
            return m.group(0)
        absu = urljoin(base_url, raw)
        target = external_map.get(absu)
        if not target and absu in same_map:
            target = same_map[absu]
        if not target:
            # Same-host original URL may map directly to a real repo path.
            p = urlparse(absu)
            if (p.hostname or "").lower() == "openrockets.com":
                candidate = p.path.lstrip("/")
                if candidate and (ROOT / candidate).is_file():
                    target = candidate
        if not target or not (ROOT / target).is_file():
            return m.group(0)
        q = m.group("q")
        return f"url({q}{rel_from_file(source_file, target)}{q})"

    def replace_import(m):
        raw = html.unescape(m.group("url").strip())
        absu = urljoin(base_url, raw)
        target = external_map.get(absu) or same_map.get(absu)
        if not target or not (ROOT / target).is_file():
            return m.group(0)
        q = m.group("q")
        return f"@import {q}{rel_from_file(source_file, target)}{q}"

    text = CSS_URL_RE.sub(replace_url, text)
    text = CSS_IMPORT_RE.sub(replace_import, text)
    return text

html_changed = 0
css_changed = 0
localized_html_refs = 0
localized_css_refs = 0

TAG_RE = re.compile(r'<(?P<tag>link|img|source|video|audio)\b[^>]*>', re.I)

for file in ROOT.rglob("*.html"):
    parts = file.relative_to(ROOT).parts
    if parts and parts[0] in {".git", ".github", "_vendor", "scripts"}:
        continue
    text = file.read_text(encoding="utf-8", errors="ignore")
    original = text

    def tag_sub(tm):
        nonlocal_tag = tm.group(0)
        tag = tm.group("tag").lower()

        # Only localize relevant link tags.
        if tag == "link":
            low = nonlocal_tag.lower()
            if not (
                'rel="stylesheet' in low or "rel='stylesheet" in low or
                'rel="icon' in low or "rel='icon" in low or
                'rel="shortcut icon' in low or "rel='shortcut icon" in low or
                'as="font' in low or "as='font" in low or
                'as="image' in low or "as='image" in low or
                'as="style' in low or "as='style" in low
            ):
                return nonlocal_tag

        def attr_sub(am):
            nonlocal localized_html_refs
            raw = am.group("url")
            target = mapped_static(raw)
            if not target or not (ROOT / target).is_file():
                return am.group(0)
            localized_html_refs += 1
            return am.group("name") + am.group("q") + rel_from_file(file, target) + am.group("q")

        tag_text = ATTR_RE.sub(attr_sub, nonlocal_tag)

        def srcset_sub(sm):
            nonlocal localized_html_refs
            out=[]
            changed=False
            for item in sm.group("value").split(","):
                item=item.strip()
                if not item:
                    continue
                bits=item.split()
                raw=bits[0]
                target=mapped_static(raw)
                if target and (ROOT / target).is_file():
                    bits[0]=rel_from_file(file,target)
                    changed=True
                    localized_html_refs += 1
                out.append(" ".join(bits))
            if not changed:
                return sm.group(0)
            return sm.group("name")+sm.group("q")+", ".join(out)+sm.group("q")

        tag_text = SRCSET_RE.sub(srcset_sub, tag_text)
        return tag_text

    text = TAG_RE.sub(tag_sub, text)

    # Inline <style> blocks: localize captured static URLs.
    def style_block_sub(m):
        content=m.group(1)
        rewritten=rewrite_css_text(content,file,"https://openrockets.com/")
        return "<style"+m.group(2)+">"+rewritten+"</style>"

    # Preserve attributes by capturing them separately.
    style_re=re.compile(r'<style(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</style>',re.I)
    def sb(m):
        body=rewrite_css_text(m.group("body"),file,"https://openrockets.com/")
        return "<style"+m.group("attrs")+">"+body+"</style>"
    text=style_re.sub(sb,text)

    if text != original:
        file.write_text(text, encoding="utf-8")
        html_changed += 1

# Rewrite all CSS, including archived vendor CSS, to use other captured local resources.
for file in ROOT.rglob("*.css"):
    parts = file.relative_to(ROOT).parts
    if parts and parts[0] in {".git", ".github", "scripts"}:
        continue

    rel = file.relative_to(ROOT).as_posix()
    if rel in reverse_external:
        base_url = reverse_external[rel]
    elif rel in reverse_same:
        base_url = reverse_same[rel]
    else:
        base_url = "https://openrockets.com/" + rel

    text=file.read_text(encoding="utf-8",errors="ignore")
    original=text
    text=rewrite_css_text(text,file,base_url)
    if text != original:
        file.write_text(text,encoding="utf-8")
        css_changed += 1

print(json.dumps({
    "html_changed": html_changed,
    "css_changed": css_changed,
    "localized_html_refs": localized_html_refs,
    "external_archive_entries": len(external_map)
}, indent=2))

# Verify the homepage now uses local recovered Stripe CSS and still leaves
# dynamic TermsFeed JS live.
index=(ROOT/"index.html").read_text(encoding="utf-8",errors="ignore")
assert "_vendor/b.stripecdn.com/" in index, "Expected localized Stripe stylesheet refs"
assert "www.termsfeed.com/public/cookie-consent/4.2.0/cookie-consent.js" in index, "TermsFeed dynamic script must remain live"
