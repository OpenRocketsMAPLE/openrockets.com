#!/usr/bin/env python3
import html as html_lib
import json
import posixpath
import re
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / ".github" / "recovery-audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUTH_REPORT = AUDIT_DIR / "authoritative-recovery-sync.json"

STRIPE_CSS = {
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/01e4fd07fe2a2b12.css":
        "vendor/b.stripecdn.com/bd89dda64c753241__01e4fd07fe2a2b12.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/112bd7743768f461.css":
        "vendor/b.stripecdn.com/a4be51b8ab24c529__112bd7743768f461.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/43d635cdf484757e.css":
        "vendor/b.stripecdn.com/03ea525f99af8346__43d635cdf484757e.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/05b42ab6014b2d13.css":
        "vendor/b.stripecdn.com/47176ab0655dbb0f__05b42ab6014b2d13.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/e07e144a3b1db9ca.css":
        "vendor/b.stripecdn.com/d938a095bea118f3__e07e144a3b1db9ca.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/3046c2816c2ffd6e.css":
        "vendor/b.stripecdn.com/9275aabfa12c5de9__3046c2816c2ffd6e.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/b793c34868bb4156.css":
        "vendor/b.stripecdn.com/3e03d3aceeac39f8__b793c34868bb4156.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/d829866f0dc0cad9.css":
        "vendor/b.stripecdn.com/de792ecb13320901__d829866f0dc0cad9.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/7fe9607f2fcd2964.css":
        "vendor/b.stripecdn.com/35f361bce1836c09__7fe9607f2fcd2964.css",
    "https://b.stripecdn.com/mkt-ssr-statics/assets/_next/static/css/5e8a245fcb880dab.css":
        "vendor/b.stripecdn.com/08bb71c05e2eaff6__5e8a245fcb880dab.css",
}

EXPLICIT_IMAGES = {
    "https://i.imgur.com/bzNtedW.png":
        "assets/external/i.imgur.com/bzNtedW__161f17bbbfd3019c1b.png",
    "https://i.imgur.com/19bWNMU.png":
        "assets/external/i.imgur.com/19bWNMU__62d0431f7d9f9d107f.png",
    "https://i.imgur.com/D9Pvn2i.png":
        "assets/external/i.imgur.com/D9Pvn2i__56f7fa0cdb7077d37f.png",
    "https://i.imgur.com/eHiWrzP.png":
        "assets/external/i.imgur.com/eHiWrzP__994961d98a630ab362.png",
    "https://i.imgur.com/sk62PQ1.jpeg":
        "assets/external/i.imgur.com/sk62PQ1__daccd40a35d4dbea30.jpg",
    "https://i.imgur.com/EqHhGcf.png":
        "assets/external/i.imgur.com/EqHhGcf__601a9ee994c3b7009f.png",
    "https://i.imgur.com/AQKACqH.png":
        "assets/external/i.imgur.com/AQKACqH__a12fcd9608af31d025.png",
    "https://scienteen.com/brand/welcomepage2.png":
        "vendor/scienteen.com/e322414522ef8878__welcomepage2.png",
}

GOOGLE_FONTS_CSS_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@300;400;500;600;700&"
    "family=Manrope:wght@400;500;600&"
    "family=Sora:wght@400;500;600&"
    "family=Space+Grotesk:wght@400;500;600&display=swap"
)
GOOGLE_FONTS_LOCAL = "vendor/fonts.googleapis.com/721baa1b99127e52__css2.css"
BOOTSTRAP_ICONS_URL = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css"
BOOTSTRAP_ICONS_LOCAL = "vendor/cdn.jsdelivr.net/f0d89529cd886929__bootstrap-icons.css"

DAILYNEWS_ORIGINAL = "https://epaper.dailynews.lk//img/ancl_logo/logo2.png"
DAILYNEWS_FALLBACK = "https://upload.wikimedia.org/wikipedia/commons/1/15/Daily_News_Sri_Lanka_logo.gif"
DAILYNEWS_DIR = ROOT / "assets" / "external" / "dailynews"

CSS_URL_RE = re.compile(
    r"url\(\s*(?P<q>[\"']?)(?P<url>[^)\"']+)(?P=q)\s*\)",
    re.I,
)
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?:url\(\s*)?(?P<q>[\"']?)(?P<url>[^\"')\s;]+)(?P=q)\s*\)?",
    re.I,
)

def rel_from_file(source_file: Path, target_rel: str) -> str:
    start = source_file.parent.relative_to(ROOT).as_posix()
    if start == ".":
        start = "."
    return posixpath.relpath(target_rel, start=start)

def require_file(rel: str):
    if not (ROOT / rel).is_file():
        raise RuntimeError(f"Required recovered file is missing: {rel}")

for rel in list(STRIPE_CSS.values()) + list(EXPLICIT_IMAGES.values()) + [
    GOOGLE_FONTS_LOCAL,
    BOOTSTRAP_ICONS_LOCAL,
    "vendor/b.stripecdn.com/0ab0832c8cc92b35__Sohne.cb178166.woff2",
    "vendor/b.stripecdn.com/ec203ee56b415fcf__SourceCodePro-Medium.f5ba3e6a.woff2",
]:
    require_file(rel)

external_map = {}
if AUTH_REPORT.is_file():
    data = json.loads(AUTH_REPORT.read_text(encoding="utf-8"))
    external_map = data.get("external_map", {}) or {}
    external_map = {
        url: rel.replace("_vendor/", "vendor/")
        for url, rel in external_map.items()
    }

external_map.update(EXPLICIT_IMAGES)
external_map.update(STRIPE_CSS)
external_map[GOOGLE_FONTS_CSS_URL] = GOOGLE_FONTS_LOCAL
external_map[BOOTSTRAP_ICONS_URL] = BOOTSTRAP_ICONS_LOCAL

reverse_external = {
    Path(rel).as_posix(): url
    for url, rel in external_map.items()
    if (ROOT / rel).is_file()
}

def valid_image_bytes(body: bytes, content_type: str) -> bool:
    ct = (content_type or "").lower()
    head = body[:1024].lstrip().lower()
    return (
        body.startswith(b"\x89PNG\r\n\x1a\n")
        or body.startswith(b"\xff\xd8\xff")
        or body.startswith((b"GIF87a", b"GIF89a"))
        or (len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP")
        or b"<svg" in head
        or "image/svg+xml" in ct
    )

def recover_dailynews_logo():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    })
    DAILYNEWS_DIR.mkdir(parents=True, exist_ok=True)

    attempts = [
        (DAILYNEWS_ORIGINAL, DAILYNEWS_DIR / "dailynews-logo.png", {"Referer": "https://epaper.dailynews.lk/"}, "original"),
        (DAILYNEWS_FALLBACK, DAILYNEWS_DIR / "dailynews-logo.gif", {"Referer": "https://commons.wikimedia.org/"}, "wikimedia-public-domain-fallback"),
    ]
    failures = []
    for url, dest, headers, source_kind in attempts:
        try:
            response = session.get(url, headers=headers, timeout=25, allow_redirects=True)
            if response.ok and valid_image_bytes(response.content, response.headers.get("content-type", "")):
                dest.write_bytes(response.content)
                return {
                    "success": True,
                    "source": source_kind,
                    "url": url,
                    "path": dest.relative_to(ROOT).as_posix(),
                    "bytes": len(response.content),
                }
            failures.append({
                "url": url,
                "status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "bytes": len(response.content),
            })
        except Exception as exc:
            failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
    return {"success": False, "failures": failures}

dailynews = recover_dailynews_logo()

html_changed = []
localized_reference_count = 0
cloudflare_tags_removed = 0

CF_SCRIPT_PATTERNS = [
    re.compile(
        r"<script\b[^>]*\bsrc=[\"'][^\"']*/cdn-cgi/challenge-platform/[^\"']*[\"'][^>]*>\s*</script>",
        re.I | re.S,
    ),
    re.compile(
        r"<script\b[^>]*\bsrc=[\"'](?:https?:)?//static\.cloudflareinsights\.com/[^\"']*[\"'][^>]*>\s*</script>",
        re.I | re.S,
    ),
]

def replace_url(text: str, source_file: Path, original: str, target: str) -> str:
    global localized_reference_count
    if original not in text:
        return text
    require_file(target)
    replacement = rel_from_file(source_file, target)
    count = text.count(original)
    localized_reference_count += count
    return text.replace(original, replacement)

for html_file in ROOT.rglob("*.html"):
    rel_parts = html_file.relative_to(ROOT).parts
    if rel_parts and rel_parts[0] in {".git", ".github", "vendor"}:
        continue

    text = html_file.read_text(encoding="utf-8", errors="ignore")
    original_text = text

    for url, target in STRIPE_CSS.items():
        text = replace_url(text, html_file, url, target)

    for url, target in EXPLICIT_IMAGES.items():
        text = replace_url(text, html_file, url, target)

    if DAILYNEWS_ORIGINAL in text and dailynews.get("success"):
        text = replace_url(text, html_file, DAILYNEWS_ORIGINAL, dailynews["path"])

    for pattern in CF_SCRIPT_PATTERNS:
        text, count = pattern.subn("", text)
        cloudflare_tags_removed += count

    if text != original_text:
        html_file.write_text(text, encoding="utf-8")
        html_changed.append(html_file.relative_to(ROOT).as_posix())

# Preserve exact recovered local DiceBear avatars instead of overwriting them at runtime.
team = ROOT / "team" / "index.html"
team_text = team.read_text(encoding="utf-8", errors="ignore")
team_original = team_text

avatar_assignment_re = re.compile(
    r"avatarImg\.src\s*=\s*\x60https://api\.dicebear\.com/9\.x/\x24\{randomStyle\}/svg\?seed=\x24\{seed\}&preset=\x24\{randomPreset\}\x60\s*;"
)
team_text, avatar_assignments_removed = avatar_assignment_re.subn(
    "avatarImg.loading = 'lazy';",
    team_text,
)

if team_text != team_original:
    team.write_text(team_text, encoding="utf-8")
    if "team/index.html" not in html_changed:
        html_changed.append("team/index.html")

team_text = team.read_text(encoding="utf-8", errors="ignore")
local_avatar_refs = re.findall(
    r'\bsrc=["\']([^"\']*assets/external/api\.dicebear\.com/[^"\']+\.svg)["\']',
    team_text,
    flags=re.I,
)
missing_avatar_files = []
for ref in local_avatar_refs:
    target = (team.parent / html_lib.unescape(ref)).resolve()
    try:
        target.relative_to(ROOT)
    except ValueError:
        missing_avatar_files.append(ref)
        continue
    if not target.is_file():
        missing_avatar_files.append(ref)

# Remove the orphaned research JavaScript error while preserving the recovered signature image.
research = ROOT / "research" / "maple" / "v1" / "index.html"
research_text = research.read_text(encoding="utf-8", errors="ignore")
research_original = research_text
research_text = research_text.replace(
    "signers.forEach((signer) => {",
    "(Array.isArray(window.signers) ? window.signers : []).forEach((signer) => {",
)
if research_text != research_original:
    research.write_text(research_text, encoding="utf-8")
    if "research/maple/v1/index.html" not in html_changed:
        html_changed.append("research/maple/v1/index.html")

# Use recovered local font/icon styles instead of remote hotlinks.
overrides = ROOT / "styles" / "overrides.css"
overrides_text = overrides.read_text(encoding="utf-8", errors="ignore")
overrides_original = overrides_text
overrides_text = overrides_text.replace(
    f"@import url('{GOOGLE_FONTS_CSS_URL}');",
    f"@import url('../{GOOGLE_FONTS_LOCAL}');",
)
overrides_text = overrides_text.replace(
    f'@import url("{GOOGLE_FONTS_CSS_URL}");',
    f'@import url("../{GOOGLE_FONTS_LOCAL}");',
)
overrides_text = overrides_text.replace(
    f"@import url('{BOOTSTRAP_ICONS_URL}');",
    f"@import url('../{BOOTSTRAP_ICONS_LOCAL}');",
)
overrides_text = overrides_text.replace(
    f'@import url("{BOOTSTRAP_ICONS_URL}");',
    f'@import url("../{BOOTSTRAP_ICONS_LOCAL}");',
)
if overrides_text != overrides_original:
    overrides.write_text(overrides_text, encoding="utf-8")

# Localize any captured dependencies referenced from CSS, including fonts.
css_changed = []
css_localized_reference_count = 0

def rewrite_css(text: str, css_file: Path, base_url: str):
    global css_localized_reference_count

    def find_local(raw: str):
        raw = html_lib.unescape(raw.strip())
        if not raw or raw.startswith(("data:", "blob:", "#")):
            return None
        absolute = urljoin(base_url, raw)
        target = external_map.get(absolute)
        if target:
            target = target.replace("_vendor/", "vendor/")
            if (ROOT / target).is_file():
                return target
        return None

    def url_sub(match):
        global css_localized_reference_count
        target = find_local(match.group("url"))
        if not target:
            return match.group(0)
        q = match.group("q")
        css_localized_reference_count += 1
        return f"url({q}{rel_from_file(css_file, target)}{q})"

    def import_sub(match):
        global css_localized_reference_count
        target = find_local(match.group("url"))
        if not target:
            return match.group(0)
        q = match.group("q")
        css_localized_reference_count += 1
        return f"@import {q}{rel_from_file(css_file, target)}{q}"

    text = CSS_URL_RE.sub(url_sub, text)
    text = CSS_IMPORT_RE.sub(import_sub, text)
    return text

for css_file in ROOT.rglob("*.css"):
    rel = css_file.relative_to(ROOT)
    if rel.parts and rel.parts[0] in {".git", ".github"}:
        continue

    rel_s = rel.as_posix()
    base_url = reverse_external.get(rel_s, "https://openrockets.com/" + rel_s)
    text = css_file.read_text(encoding="utf-8", errors="ignore")
    new_text = rewrite_css(text, css_file, base_url)
    if new_text != text:
        css_file.write_text(new_text, encoding="utf-8")
        css_changed.append(rel_s)

# Validate the local MAPLE feed cache.
maple_feed = ROOT / "data" / "maple-feed.json"
maple_feed_valid = False
maple_feed_items = None
if maple_feed.is_file():
    try:
        feed_data = json.loads(maple_feed.read_text(encoding="utf-8"))
        if isinstance(feed_data, list):
            maple_feed_items = len(feed_data)
            maple_feed_valid = True
        elif isinstance(feed_data, dict):
            items = feed_data.get("items")
            maple_feed_items = len(items) if isinstance(items, list) else None
            maple_feed_valid = True
    except Exception:
        pass

# Final validation gates.
index = (ROOT / "index.html").read_text(encoding="utf-8", errors="ignore")
research_final = research.read_text(encoding="utf-8", errors="ignore")
team_final = team.read_text(encoding="utf-8", errors="ignore")
overrides_final = overrides.read_text(encoding="utf-8", errors="ignore")

known_broken_homepage_urls = [
    "https://i.imgur.com/bzNtedW.png",
    "https://i.imgur.com/19bWNMU.png",
    "https://i.imgur.com/D9Pvn2i.png",
    "https://i.imgur.com/eHiWrzP.png",
    "https://i.imgur.com/sk62PQ1.jpeg",
    "https://i.imgur.com/EqHhGcf.png",
    "https://scienteen.com/brand/welcomepage2.png",
]
remaining = [url for url in known_broken_homepage_urls if url in index]
if remaining:
    raise SystemExit(f"Known broken homepage hotlinks remain: {remaining}")

all_html_text = "\n".join(
    p.read_text(encoding="utf-8", errors="ignore")
    for p in ROOT.rglob("*.html")
    if ".git" not in p.parts and ".github" not in p.parts and "vendor" not in p.parts
)
remote_stripe = [url for url in STRIPE_CSS if url in all_html_text]
if remote_stripe:
    raise SystemExit(f"Remote Stripe CSS links remain: {remote_stripe}")

if re.search(
    r"avatarImg\.src\s*=\s*\x60https://api\.dicebear\.com/",
    team_final,
):
    raise SystemExit("Team page still overwrites recovered avatars with DiceBear network URLs")

if len(local_avatar_refs) < 60:
    raise SystemExit(f"Too few local recovered team avatars: {len(local_avatar_refs)}")
if missing_avatar_files:
    raise SystemExit(f"Missing recovered avatar files: {missing_avatar_files[:20]}")

if "https://i.imgur.com/AQKACqH.png" in research_final:
    raise SystemExit("Research page still hotlinks the broken Imgur image")
if "signers.forEach((signer)" in research_final:
    raise SystemExit("Unsafe research signers renderer remains")

if GOOGLE_FONTS_CSS_URL in overrides_final:
    raise SystemExit("Remote Google Fonts import remains in overrides.css")
if BOOTSTRAP_ICONS_URL in overrides_final:
    raise SystemExit("Remote Bootstrap Icons import remains in overrides.css")

report = {
    "success": True,
    "html_changed": sorted(set(html_changed)),
    "html_localized_reference_count": localized_reference_count,
    "css_changed": sorted(set(css_changed)),
    "css_localized_reference_count": css_localized_reference_count,
    "team_avatar_assignments_removed": avatar_assignments_removed,
    "team_local_avatar_count": len(local_avatar_refs),
    "team_missing_local_avatar_files": missing_avatar_files,
    "dailynews_logo": dailynews,
    "maple_feed_valid": maple_feed_valid,
    "maple_feed_items": maple_feed_items,
    "cloudflare_script_tags_removed": cloudflare_tags_removed,
}

(AUDIT_DIR / "runtime-asset-repair.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print(json.dumps(report, indent=2, ensure_ascii=False))
