#!/usr/bin/env python3
import hashlib
import html
import json
import mimetypes
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / ".github" / "recovery-audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
REPORT = AUDIT_DIR / "external-image-cache.json"

CANONICAL_HTML = [
    ROOT / "index.html",
    ROOT / "join.html",
    ROOT / "team" / "index.html",
    ROOT / "team" / "management-profile.html",
    ROOT / "our-communities" / "index.html",
    ROOT / "merch" / "index.html",
    ROOT / "merch" / "cart.html",
    ROOT / "merch" / "product.html",
    ROOT / "research" / "maple" / "v1" / "index.html",
    ROOT / "magazinesoftware" / "signup" / "index.html",
]

AUTH_REPORT = AUDIT_DIR / "authoritative-recovery-sync.json"
AUTH_MAP = {}
if AUTH_REPORT.exists():
    try:
        AUTH_MAP = json.loads(AUTH_REPORT.read_text(encoding="utf-8")).get("external_map", {}) or {}
    except Exception:
        AUTH_MAP = {}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

IMG_ATTR_RE = re.compile(
    r'(?P<prefix>\b(?:src|poster|data-src|data-lazy-src|data-original)\s*=\s*(?P<q>["\']))'
    r'(?P<url>https?://[^"\']+)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

SRCSET_RE = re.compile(
    r'(?P<prefix>\b(?:srcset|data-srcset)\s*=\s*(?P<q>["\']))'
    r'(?P<value>[^"\']+)'
    r'(?P<suffix>(?P=q))',
    re.I,
)

STYLE_URL_RE = re.compile(
    r'url\(\s*(?P<q>["\']?)(?P<url>https?://[^)"\']+)(?P=q)\s*\)',
    re.I,
)

def is_same_site(url):
    try:
        return (urlparse(url).hostname or "").lower() == "openrockets.com"
    except Exception:
        return False

def body_ext(body, content_type, url):
    ct = (content_type or "").lower().split(";")[0].strip()
    head = body[:512].lstrip()

    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if body.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return ".webp"
    if body.startswith(b"\x00\x00\x01\x00"):
        return ".ico"

    text = head.decode("utf-8", errors="ignore").lower()
    if "<svg" in text:
        return ".svg"

    if ct.startswith("image/"):
        guessed = mimetypes.guess_extension(ct)
        if guessed == ".jpe":
            guessed = ".jpg"
        if guessed:
            return guessed

    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    if suffix in {".png",".jpg",".jpeg",".webp",".gif",".svg",".ico",".avif"}:
        return ".jpg" if suffix == ".jpeg" else suffix

    return None

def valid_image(body, content_type, url):
    ext = body_ext(body, content_type, url)
    if not ext or not body:
        return False, None
    if body[:2048].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return False, None
    return True, ext

def archived_candidate(url):
    mapped = AUTH_MAP.get(url)
    candidates = []

    if mapped:
        mapped_path = mapped.replace("\\", "/")
        if mapped_path.startswith("_vendor/"):
            mapped_path = "vendor/" + mapped_path[len("_vendor/"):]
        candidates.append(ROOT / mapped_path)

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    basename = Path(unquote(parsed.path)).name
    if host and basename:
        host_dir = ROOT / "vendor" / host
        if host_dir.is_dir():
            candidates.extend(sorted(host_dir.glob(f"*__{basename}")))

    for candidate in candidates:
        if candidate.is_file():
            body = candidate.read_bytes()
            ok, ext = valid_image(body, mimetypes.guess_type(candidate.name)[0] or "", url)
            if ok:
                return candidate, ext
    return None, None

def local_output_path(url, ext):
    parsed = urlparse(url)
    host = re.sub(r"[^A-Za-z0-9.-]+", "_", (parsed.hostname or "external").lower())
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:18]
    basename = Path(unquote(parsed.path)).stem
    basename = re.sub(r"[^A-Za-z0-9._-]+", "_", basename)[:60].strip("._-")
    if not basename:
        basename = "image"
    return ROOT / "assets" / "external" / host / f"{basename}__{digest}{ext}"

def relative_from(html_file, target):
    start = html_file.parent.relative_to(ROOT).as_posix()
    start = "." if start == "." else start
    return posixpath.relpath(target.relative_to(ROOT).as_posix(), start=start)

cache = {}
fetch_log = []

def cache_url(raw_url):
    decoded = html.unescape(raw_url)
    if decoded in cache:
        return cache[decoded]

    if is_same_site(decoded):
        cache[decoded] = None
        return None

    source, ext = archived_candidate(decoded)
    if source is not None:
        target = local_output_path(decoded, ext)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != source.read_bytes():
            target.write_bytes(source.read_bytes())
        fetch_log.append({
            "url": decoded,
            "result": "reused-recovered-copy",
            "source": source.relative_to(ROOT).as_posix(),
            "target": target.relative_to(ROOT).as_posix(),
        })
        cache[decoded] = target
        return target

    try:
        response = SESSION.get(decoded, timeout=20, allow_redirects=True)
        body = response.content
        ok, ext = valid_image(body, response.headers.get("content-type", ""), str(response.url))
        if response.status_code == 200 and ok:
            target = local_output_path(decoded, ext)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            fetch_log.append({
                "url": decoded,
                "result": "downloaded",
                "status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "bytes": len(body),
                "final_url": str(response.url),
                "target": target.relative_to(ROOT).as_posix(),
            })
            cache[decoded] = target
            return target

        fetch_log.append({
            "url": decoded,
            "result": "unresolved",
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "bytes": len(body),
            "final_url": str(response.url),
        })
    except Exception as exc:
        fetch_log.append({
            "url": decoded,
            "result": "error",
            "error": f"{type(exc).__name__}: {exc}",
        })

    cache[decoded] = None
    return None

changed_html = []
for html_file in CANONICAL_HTML:
    if not html_file.is_file():
        continue

    source = html_file.read_text(encoding="utf-8", errors="ignore")
    original = source

    def attr_sub(match):
        raw = match.group("url")
        target = cache_url(raw)
        if target is None:
            return match.group(0)
        return (
            match.group("prefix")
            + relative_from(html_file, target)
            + match.group("suffix")
        )

    source = IMG_ATTR_RE.sub(attr_sub, source)

    def srcset_sub(match):
        rewritten = []
        for item in match.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            raw = bits[0]
            if raw.startswith(("http://","https://")):
                target = cache_url(raw)
                if target is not None:
                    raw = relative_from(html_file, target)
            rewritten.append(" ".join([raw] + bits[1:]))
        return match.group("prefix") + ", ".join(rewritten) + match.group("suffix")

    source = SRCSET_RE.sub(srcset_sub, source)

    def style_sub(match):
        raw = match.group("url")
        target = cache_url(raw)
        if target is None:
            return match.group(0)
        q = match.group("q")
        return f"url({q}{relative_from(html_file, target)}{q})"

    source = STYLE_URL_RE.sub(style_sub, source)

    if source != original:
        html_file.write_text(source, encoding="utf-8")
        changed_html.append(html_file.relative_to(ROOT).as_posix())

# Fix the known Research runtime crash without inventing signer data.
research = ROOT / "research" / "maple" / "v1" / "index.html"
research_fix = False
if research.is_file():
    source = research.read_text(encoding="utf-8", errors="ignore")
    if "signers.forEach" in source and not re.search(r"\b(?:const|let|var)\s+signers\s*=", source):
        marker = """    /* =========================================================
       RENDER SIGNATURES
       ========================================================= */
"""
        if marker in source:
            source = source.replace(
                marker,
                """    const signers = [];

""" + marker,
                1,
            )
            research.write_text(source, encoding="utf-8")
            research_fix = True
            if research.relative_to(ROOT).as_posix() not in changed_html:
                changed_html.append(research.relative_to(ROOT).as_posix())

# Override Stripe's cross-origin fonts with validated local recovered copies.
css = ROOT / "styles" / "overrides.css"
font_fix = False
font_marker = "/* OpenRockets recovered local font fallbacks */"
if css.is_file() and font_marker not in css.read_text(encoding="utf-8", errors="ignore"):
    sohne = ROOT / "vendor" / "b.stripecdn.com" / "0ab0832c8cc92b35__Sohne.cb178166.woff2"
    source_code = ROOT / "vendor" / "b.stripecdn.com" / "ec203ee56b415fcf__SourceCodePro-Medium.f5ba3e6a.woff2"

    blocks = []
    if sohne.is_file():
        blocks.append("""@font-face {
  font-family: "sohne-var";
  src: url("../vendor/b.stripecdn.com/0ab0832c8cc92b35__Sohne.cb178166.woff2") format("woff2");
  font-weight: 1 1000;
  font-style: normal;
  font-display: swap;
}""")

    if source_code.is_file():
        blocks.append("""@font-face {
  font-family: "SourceCodePro";
  src: url("../vendor/b.stripecdn.com/ec203ee56b415fcf__SourceCodePro-Medium.f5ba3e6a.woff2") format("woff2");
  font-weight: 500;
  font-style: normal;
  font-display: swap;
}""")

    if blocks:
        old = css.read_text(encoding="utf-8")
        css.write_text(
            font_marker + "\n" + "\n\n".join(blocks) + "\n\n" + old,
            encoding="utf-8",
        )
        font_fix = True

resolved = [x for x in fetch_log if x["result"] in {"downloaded","reused-recovered-copy"}]
unresolved = [x for x in fetch_log if x["result"] not in {"downloaded","reused-recovered-copy"}]

REPORT.write_text(json.dumps({
    "changed_html": changed_html,
    "changed_html_count": len(changed_html),
    "font_fix_applied": font_fix,
    "research_signers_fail_safe_applied": research_fix,
    "unique_external_images_seen": len(cache),
    "resolved_count": len(resolved),
    "unresolved_count": len(unresolved),
    "resolved": resolved,
    "unresolved": unresolved,
}, indent=2, ensure_ascii=False), encoding="utf-8")

print(json.dumps({
    "changed_html_count": len(changed_html),
    "font_fix_applied": font_fix,
    "research_signers_fail_safe_applied": research_fix,
    "unique_external_images_seen": len(cache),
    "resolved_count": len(resolved),
    "unresolved_count": len(unresolved),
}, indent=2))
