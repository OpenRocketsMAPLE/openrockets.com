#!/usr/bin/env python3
import hashlib
import html
import json
import mimetypes
import os
import posixpath
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "external"
REPORT = ROOT / ".github" / "recovery-audit" / "external-image-integration.json"
AUTH_REPORT = ROOT / ".github" / "recovery-audit" / "authoritative-recovery-sync.json"
FEED_URL = "https://maplelicense.substack.com/feed"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131 Safari/537.36"
)

MAX_BYTES = 20 * 1024 * 1024
TIMEOUT = 20

external_map = {}
if AUTH_REPORT.exists():
    try:
        external_map = json.loads(AUTH_REPORT.read_text(encoding="utf-8")).get("external_archive_map", {}) or {}
    except Exception:
        external_map = {}

downloaded = {}
reused_vendor = {}
same_host_localized = {}
failed = {}
changed_files = set()

def request_bytes(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://openrockets.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        ctype = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(f"resource exceeds {MAX_BYTES} bytes")
        final_url = response.geturl()
        return data, ctype, final_url

def image_kind(data: bytes, ctype: str, url: str):
    head = data[:2048].lstrip()
    lower = head.lower()

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) >= 12 and data[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif"
    if lower.startswith(b"<svg") or b"<svg" in lower[:600]:
        return ".svg"
    if ctype.startswith("image/"):
        ext = mimetypes.guess_extension(ctype) or ""
        if ext == ".jpe":
            ext = ".jpg"
        if ext:
            return ext

    ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if ext in {".png",".jpg",".jpeg",".gif",".webp",".svg",".avif",".ico"}:
        # Only trust the extension when the body does not look like HTML.
        if b"<html" not in lower[:700] and not lower.startswith(b"<!doctype html"):
            return ".jpg" if ext == ".jpeg" else ext

    return None

def valid_existing_image(path: Path):
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        data = path.read_bytes()[:4096]
    except Exception:
        return False
    ext = path.suffix.lower()
    lower = data.lstrip().lower()
    if b"<html" in lower[:800] or lower.startswith(b"<!doctype html"):
        return False
    if ext == ".svg":
        return lower.startswith(b"<svg") or b"<svg" in lower[:1200]
    if ext == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {".jpg",".jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if ext == ".avif":
        return len(data) >= 12 and data[4:12] in (b"ftypavif", b"ftypavis")
    if ext == ".ico":
        return data[:4] == b"\x00\x00\x01\x00"
    return True

def rel_for_html(html_path: Path, target: Path):
    rel = os.path.relpath(target, html_path.parent)
    return Path(rel).as_posix()

def normalize_remote(raw: str):
    return html.unescape(raw.strip())

def localize_image_url(raw: str, source_file: Path):
    decoded = normalize_remote(raw)
    if not decoded or decoded.startswith(("data:", "blob:", "#")):
        return None

    parsed = urllib.parse.urlparse(decoded)
    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()

    # Same-host files belong in their original repository paths when recovered.
    if host == "openrockets.com":
        path = urllib.parse.unquote(parsed.path or "").lstrip("/")
        candidate = ROOT / path
        if valid_existing_image(candidate):
            same_host_localized[decoded] = candidate.relative_to(ROOT).as_posix()
            return rel_for_html(source_file, candidate)
        return None

    # Prefer a validated copy already captured by the authoritative browser crawl.
    mapped = external_map.get(decoded)
    if mapped:
        mapped = mapped.replace("\\", "/")
        if mapped.startswith("_vendor/"):
            mapped = "vendor/" + mapped[len("_vendor/"):]
        candidate = ROOT / mapped
        if valid_existing_image(candidate):
            reused_vendor[decoded] = candidate.relative_to(ROOT).as_posix()
            return rel_for_html(source_file, candidate)

    if decoded in downloaded:
        candidate = ROOT / downloaded[decoded]
        return rel_for_html(source_file, candidate)

    try:
        data, ctype, final_url = request_bytes(decoded)
        ext = image_kind(data, ctype, final_url)
        if not ext:
            failed[decoded] = f"not a valid image: content-type={ctype!r}"
            return None

        host_dir = re.sub(r"[^a-z0-9._-]+", "_", host) or "external"
        digest = hashlib.sha256(decoded.encode("utf-8")).hexdigest()[:20]
        target = ASSET_ROOT / host_dir / f"{digest}{ext}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

        downloaded[decoded] = target.relative_to(ROOT).as_posix()
        return rel_for_html(source_file, target)
    except Exception as exc:
        failed[decoded] = f"{type(exc).__name__}: {exc}"
        return None

ATTR_RE = re.compile(
    r'(?P<prefix><(?:img|source|video)\b[^>]*?\b(?:src|poster|data-src|data-lazy-src|data-original)\s*=\s*(?P<q>["\']))'
    r'(?P<url>[^"\']+)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

SRCSET_RE = re.compile(
    r'(?P<prefix>\b(?:srcset|data-srcset)\s*=\s*(?P<q>["\']))'
    r'(?P<value>[^"\']+)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

PROFILE_IMAGE_RE = re.compile(
    r'(?P<prefix>\bimage\s*:\s*(?P<q>["\']))'
    r'(?P<url>https?://[^"\']+)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

CSS_REMOTE_URL_RE = re.compile(
    r'url\(\s*(?P<q>["\']?)(?P<url>https?://[^)"\']+)(?P=q)\s*\)',
    re.I,
)

html_files = [
    p for p in ROOT.rglob("*.html")
    if ".git" not in p.parts
    and ".github" not in p.parts
    and "vendor" not in p.parts
    and "_vendor" not in p.parts
]

for path in html_files:
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    def attr_sub(m):
        new = localize_image_url(m.group("url"), path)
        if not new:
            return m.group(0)
        return m.group("prefix") + new + m.group("suffix")

    text = ATTR_RE.sub(attr_sub, text)

    def srcset_sub(m):
        parts_out = []
        changed = False
        for item in m.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            raw_url = bits[0]
            new = localize_image_url(raw_url, path)
            if new:
                bits[0] = new
                changed = True
            parts_out.append(" ".join(bits))
        if not changed:
            return m.group(0)
        return m.group("prefix") + ", ".join(parts_out) + m.group("suffix")

    text = SRCSET_RE.sub(srcset_sub, text)

    # Dynamic management-profile portrait URLs live inside a JS object.
    def profile_sub(m):
        new = localize_image_url(m.group("url"), path)
        if not new:
            return m.group(0)
        return m.group("prefix") + new + m.group("suffix")

    text = PROFILE_IMAGE_RE.sub(profile_sub, text)

    # Only localize absolute CSS url(...) values if they resolve to a valid image.
    def css_sub(m):
        new = localize_image_url(m.group("url"), path)
        if not new:
            return m.group(0)
        q = m.group("q")
        return f"url({q}{new}{q})"

    text = CSS_REMOTE_URL_RE.sub(css_sub, text)

    if text != original:
        path.write_text(text, encoding="utf-8")
        changed_files.add(path.relative_to(ROOT).as_posix())

# External image URLs can also live in local CSS.
for path in [
    p for p in ROOT.rglob("*.css")
    if ".git" not in p.parts and ".github" not in p.parts and "vendor" not in p.parts
]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    def css_sub(m):
        new = localize_image_url(m.group("url"), path)
        if not new:
            return m.group(0)
        q = m.group("q")
        return f"url({q}{new}{q})"

    text = CSS_REMOTE_URL_RE.sub(css_sub, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed_files.add(path.relative_to(ROOT).as_posix())

# Add a local exact-family fallback for Stripe's Sohne variable font.
overrides = ROOT / "styles" / "overrides.css"
sohne = next(iter((ROOT / "vendor" / "b.stripecdn.com").glob("*Sohne*.woff2")), None)
source_code = next(iter((ROOT / "vendor" / "b.stripecdn.com").glob("*SourceCodePro*.woff2")), None)
if overrides.exists() and sohne and valid_existing_image(sohne) is False:
    # Font validation is different from images: just ensure it is a non-HTML binary.
    head = sohne.read_bytes()[:512].lstrip().lower()
    font_ok = bool(sohne.stat().st_size > 1000 and b"<html" not in head)
else:
    font_ok = bool(sohne and sohne.exists() and sohne.stat().st_size > 1000)

if overrides.exists() and font_ok:
    css = overrides.read_text(encoding="utf-8")
    marker = "/* recovered-local-font-fallbacks */"
    if marker not in css:
        font_rel = os.path.relpath(sohne, overrides.parent).replace(os.sep, "/")
        block = f'''{marker}
@font-face {{
  font-family: "sohne-var";
  src: url("{font_rel}") format("woff2-variations");
  font-weight: 1 1000;
  font-style: normal;
  font-display: swap;
}}
'''
        if source_code and source_code.exists() and source_code.stat().st_size > 1000:
            sc_rel = os.path.relpath(source_code, overrides.parent).replace(os.sep, "/")
            block += f'''@font-face {{
  font-family: "SourceCodePro";
  src: url("{sc_rel}") format("woff2");
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}}
'''
        overrides.write_text(block + "\n" + css, encoding="utf-8")
        changed_files.add(overrides.relative_to(ROOT).as_posix())

# Restore the MAPLE feed cache from the current live RSS feed.
feed_result = {"success": False}
def fetch_text(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/rss+xml,application/xml,text/xml,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return response.read(8 * 1024 * 1024).decode("utf-8", errors="replace")

feed_xml = None
feed_error = None
for candidate in (FEED_URL, "https://proxy.cors.dev/" + FEED_URL):
    try:
        feed_xml = fetch_text(candidate)
        if "<rss" in feed_xml.lower() or "<feed" in feed_xml.lower():
            feed_result["fetched_from"] = candidate
            break
        feed_xml = None
    except Exception as exc:
        feed_error = f"{type(exc).__name__}: {exc}"

if feed_xml:
    try:
        root = ET.fromstring(feed_xml)
        items = []
        for item in root.iter():
            if item.tag.split("}")[-1].lower() != "item":
                continue
            vals = {}
            enclosure = None
            for child in list(item):
                name = child.tag.split("}")[-1]
                text_value = (child.text or "").strip()
                if name in {"title","description","encoded","pubDate","published","link"} and text_value:
                    vals[name] = text_value
                if name in {"enclosure","thumbnail","content"}:
                    url = child.attrib.get("url")
                    typ = child.attrib.get("type","")
                    if url and (typ.startswith("image/") or name != "enclosure"):
                        enclosure = url
            link = vals.get("link","")
            if not link.startswith(("http://","https://")):
                continue
            items.append({
                "title": vals.get("title","MAPLE update"),
                "description": vals.get("description",""),
                "content": vals.get("encoded", vals.get("description","")),
                "image": enclosure or "",
                "pubDate": vals.get("pubDate", vals.get("published","")),
                "link": link,
            })
        if items:
            data_dir = ROOT / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            cache = data_dir / "maple-feed.json"
            cache.write_text(
                json.dumps({
                    "source": FEED_URL,
                    "generated_at_unix": int(time.time()),
                    "items": items[:20],
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            changed_files.add(cache.relative_to(ROOT).as_posix())

            index = ROOT / "index.html"
            if index.exists():
                t = index.read_text(encoding="utf-8", errors="ignore")
                old = "const CACHE_URL = 'https://raw.githubusercontent.com/OpenRockets-Press/openrockets.com/main/data/maple-feed.json';"
                new = "const CACHE_URL = 'data/maple-feed.json';"
                if old in t:
                    index.write_text(t.replace(old, new), encoding="utf-8")
                    changed_files.add("index.html")

            feed_result.update({"success": True, "item_count": len(items[:20])})
        else:
            feed_result["error"] = "feed parsed but contained no usable items"
    except Exception as exc:
        feed_result["error"] = f"{type(exc).__name__}: {exc}"
else:
    feed_result["error"] = feed_error or "unable to fetch RSS feed"

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps({
    "generated_at_unix": int(time.time()),
    "changed_files": sorted(changed_files),
    "same_host_localized_count": len(same_host_localized),
    "vendor_reused_count": len(reused_vendor),
    "downloaded_count": len(downloaded),
    "failed_count": len(failed),
    "same_host_localized": same_host_localized,
    "vendor_reused": reused_vendor,
    "downloaded": downloaded,
    "failed": failed,
    "feed": feed_result,
    "local_sohne_font": sohne.relative_to(ROOT).as_posix() if sohne else None,
}, indent=2, ensure_ascii=False), encoding="utf-8")

print(json.dumps({
    "changed_file_count": len(changed_files),
    "same_host_localized_count": len(same_host_localized),
    "vendor_reused_count": len(reused_vendor),
    "downloaded_count": len(downloaded),
    "failed_count": len(failed),
    "feed": feed_result,
    "sohne_fallback_added": bool(sohne and overrides.exists()),
}, indent=2))
