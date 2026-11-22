#!/usr/bin/env python3
import html
import json
import os
import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / ".github" / "recovery-audit" / "authoritative-recovery-sync.json"

TEXT_SUFFIXES = {
    ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".json", ".xml",
    ".txt", ".md", ".py", ".yml", ".yaml", ".svg", ".map", ".webmanifest"
}
SAFE_LOCAL_EXTS = {
    ".css",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".mov",
    ".pdf", ".json", ".xml", ".webmanifest",
}
DYNAMIC_SCRIPT_HOSTS = {
    "www.termsfeed.com",
    "elfsightcdn.com",
    "static.elfsight.com",
    "www.jotform.com",
    "js.hcaptcha.com",
    "www.google.com",
    "www.gstatic.com",
    "www.youtube.com",
    "challenges.cloudflare.com",
}

def sha256(path: Path):
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def migrate_vendor_tree():
    legacy = ROOT / "_vendor"
    safe = ROOT / "vendor"
    stats = {"moved": 0, "deduped": 0, "overwritten": 0}

    safe.mkdir(parents=True, exist_ok=True)
    if not legacy.exists():
        return stats

    for src in sorted(legacy.rglob("*")):
        if not src.is_file():
            continue
        rel = src.relative_to(legacy)
        dst = safe / rel
        dst.parent.mkdir(parents=True, exist_ok=True)

        if dst.exists():
            if src.read_bytes() == dst.read_bytes():
                src.unlink()
                stats["deduped"] += 1
            else:
                # The just-recovered legacy file is authoritative for this pass.
                shutil.copy2(src, dst)
                src.unlink()
                stats["overwritten"] += 1
        else:
            shutil.move(str(src), str(dst))
            stats["moved"] += 1

    shutil.rmtree(legacy, ignore_errors=True)
    return stats

def replace_legacy_vendor_refs():
    changed = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        rel_parts = p.relative_to(ROOT).parts
        if rel_parts and rel_parts[0] == ".github":
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES and p.name not in {"CNAME", ".nojekyll"}:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        new = text.replace("/_vendor/", "/vendor/").replace("_vendor/", "vendor/")
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(p.relative_to(ROOT).as_posix())
    return changed

def patch_recovery_pipeline():
    changed = []

    auth = ROOT / ".github" / "scripts" / "authoritative_recovery_sync.py"
    if auth.exists():
        text = auth.read_text(encoding="utf-8")
        original = text
        text = text.replace(
            'EXCLUDE_SCAN_TOP = {".git", ".github", "_vendor"}',
            'EXCLUDE_SCAN_TOP = {".git", ".github", "_vendor", "vendor"}',
        )
        text = text.replace(
            'return Path("_vendor") / host / f"{digest}__{raw_name}"',
            'return Path("vendor") / host / f"{digest}__{raw_name}"',
        )
        text = text.replace(
            'if rel.parts and rel.parts[0] in {".git", ".github", "_vendor"}:',
            'if rel.parts and rel.parts[0] in {".git", ".github", "_vendor", "vendor"}:',
        )
        if text != original:
            auth.write_text(text, encoding="utf-8")
            changed.append(auth.relative_to(ROOT).as_posix())

    post = ROOT / ".github" / "scripts" / "postprocess_recovered_site.py"
    if post.exists():
        text = post.read_text(encoding="utf-8")
        original = text
        text = text.replace(
            'EXCLUDE_TOP = {".git", ".github", "_vendor"}',
            'EXCLUDE_TOP = {".git", ".github", "_vendor", "vendor"}',
        )
        if text != original:
            post.write_text(text, encoding="utf-8")
            changed.append(post.relative_to(ROOT).as_posix())

    # Workflow files are intentionally not modified here. GitHub App tokens
    # used by Actions cannot push workflow-file changes without workflow
    # permission, and asset integration must never depend on that permission.

    return changed

vendor_stats = migrate_vendor_tree()
legacy_ref_changes = replace_legacy_vendor_refs()
pipeline_changes = patch_recovery_pipeline()

if not REPORT.exists():
    raise SystemExit(f"Missing authoritative report: {REPORT}")

data = json.loads(REPORT.read_text(encoding="utf-8"))

# Any paths embedded in the just-written report should now point at vendor/.
def rewrite_json_paths(value):
    if isinstance(value, dict):
        return {k: rewrite_json_paths(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite_json_paths(v) for v in value]
    if isinstance(value, str):
        return value.replace("/_vendor/", "/vendor/").replace("_vendor/", "vendor/")
    return value

data = rewrite_json_paths(data)
REPORT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

external_map = data.get("external_map", {}) or {}
same_map = data.get("same_host_map", {}) or {}
reverse_external = {Path(v).as_posix(): u for u, v in external_map.items()}
reverse_same = {Path(v).as_posix(): u for u, v in same_map.items()}

def mapped_target(url):
    if not url:
        return None
    u = html.unescape(url.strip())
    rel = external_map.get(u)
    if not rel:
        return None
    rel = rel.replace("_vendor/", "vendor/")
    p = ROOT / rel
    if not p.is_file():
        return None

    ext = Path(urlparse(u).path).suffix.lower() or p.suffix.lower()
    if ext not in SAFE_LOCAL_EXTS and p.suffix.lower() not in SAFE_LOCAL_EXTS:
        return None
    return rel

def relative_from(source: Path, target_rel: str):
    start = source.parent.relative_to(ROOT).as_posix()
    if start == ".":
        start = "."
    return posixpath.relpath(target_rel, start=start)

ATTR_RE = re.compile(
    r'(?P<name>\b(?:href|src|poster|data-src|data-lazy-src|data-original|data-bg|data)\s*=\s*)'
    r'(?P<q>["\'])(?P<url>[^"\']+)(?P=q)',
    re.I,
)
SRCSET_RE = re.compile(
    r'(?P<name>\b(?:srcset|data-srcset)\s*=\s*)(?P<q>["\'])(?P<value>[^"\']+)(?P=q)',
    re.I,
)
TAG_RE = re.compile(r'<(?P<tag>link|img|source|video|audio|input|object)\b[^>]*>', re.I)
CSS_URL_RE = re.compile(
    r'url\(\s*(?P<q>["\']?)(?P<url>[^)"\']+)(?P=q)\s*\)',
    re.I,
)
CSS_IMPORT_RE = re.compile(
    r'@import\s+(?:url\(\s*)?(?P<q>["\']?)(?P<url>[^"\')\s;]+)(?P=q)\s*\)?',
    re.I,
)

html_files_changed = 0
html_refs_localized = 0
css_files_changed = 0
css_refs_localized = 0

def localize_tag(tag_text: str, source_file: Path):
    global html_refs_localized

    tag_match = re.match(r'<\s*([A-Za-z0-9:-]+)', tag_text)
    tag = tag_match.group(1).lower() if tag_match else ""

    if tag == "link":
        lower = tag_text.lower()
        allowed = (
            "stylesheet" in lower
            or "icon" in lower
            or ('rel="preload"' in lower and any(x in lower for x in ('as="font"', 'as="image"', 'as="style"')))
            or ("rel='preload'" in lower and any(x in lower for x in ("as='font'", "as='image'", "as='style'")))
        )
        if not allowed:
            return tag_text

    def attr_sub(m):
        global html_refs_localized
        raw = m.group("url")
        target = mapped_target(raw)
        if not target:
            return m.group(0)

        # Never turn an origin-sensitive third-party runtime script into a local file.
        parsed = urlparse(html.unescape(raw))
        if tag == "script" or (parsed.hostname or "").lower() in DYNAMIC_SCRIPT_HOSTS and Path(target).suffix.lower() in {".js", ".mjs", ".cjs"}:
            return m.group(0)

        html_refs_localized += 1
        return m.group("name") + m.group("q") + relative_from(source_file, target) + m.group("q")

    out = ATTR_RE.sub(attr_sub, tag_text)

    def srcset_sub(m):
        global html_refs_localized
        items = []
        changed = False
        for item in m.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            target = mapped_target(bits[0])
            if target:
                bits[0] = relative_from(source_file, target)
                changed = True
                html_refs_localized += 1
            items.append(" ".join(bits))
        if not changed:
            return m.group(0)
        return m.group("name") + m.group("q") + ", ".join(items) + m.group("q")

    out = SRCSET_RE.sub(srcset_sub, out)
    return out

def rewrite_css_text(text: str, source_file: Path, base_url: str):
    global css_refs_localized

    def resolve(raw):
        raw = html.unescape(raw.strip())
        if not raw or raw.startswith(("data:", "blob:", "#")):
            return None, raw

        absolute = urljoin(base_url, raw)
        target = external_map.get(absolute)
        if target:
            target = target.replace("_vendor/", "vendor/")
            if (ROOT / target).is_file():
                return target, absolute

        target = same_map.get(absolute)
        if target and (ROOT / target).is_file():
            return target, absolute

        p = urlparse(absolute)
        if (p.hostname or "").lower() == "openrockets.com":
            candidate = p.path.lstrip("/")
            if candidate and (ROOT / candidate).is_file():
                return candidate, absolute

        return None, absolute

    def url_sub(m):
        global css_refs_localized
        raw = m.group("url")
        target, absolute = resolve(raw)
        q = m.group("q")
        if target:
            css_refs_localized += 1
            return f"url({q}{relative_from(source_file, target)}{q})"

        # If this is archived third-party CSS and a relative dependency was not
        # captured, preserve its original origin rather than accidentally making
        # it relative to GitHub Pages.
        rel = source_file.relative_to(ROOT).as_posix()
        if rel in reverse_external and raw and not urlparse(raw).scheme and not raw.startswith("//"):
            return f"url({q}{absolute}{q})"
        return m.group(0)

    def import_sub(m):
        global css_refs_localized
        raw = m.group("url")
        target, absolute = resolve(raw)
        q = m.group("q")
        if target:
            css_refs_localized += 1
            return f"@import {q}{relative_from(source_file, target)}{q}"

        rel = source_file.relative_to(ROOT).as_posix()
        if rel in reverse_external and raw and not urlparse(raw).scheme and not raw.startswith("//"):
            return f"@import {q}{absolute}{q}"
        return m.group(0)

    text = CSS_URL_RE.sub(url_sub, text)
    text = CSS_IMPORT_RE.sub(import_sub, text)
    return text

for p in ROOT.rglob("*.html"):
    rel = p.relative_to(ROOT)
    if rel.parts and rel.parts[0] in {".git", ".github", "vendor", "_vendor"}:
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    original = text
    text = TAG_RE.sub(lambda m: localize_tag(m.group(0), p), text)

    def inline_css_sub(m):
        raw = m.group("url")
        target = mapped_target(raw)
        if not target:
            return m.group(0)
        q = m.group("q")
        return f"url({q}{relative_from(p, target)}{q})"

    text = CSS_URL_RE.sub(inline_css_sub, text)
    if text != original:
        p.write_text(text, encoding="utf-8")
        html_files_changed += 1

for p in ROOT.rglob("*.css"):
    rel = p.relative_to(ROOT)
    if rel.parts and rel.parts[0] in {".git", ".github"}:
        continue

    rel_s = rel.as_posix()
    if rel_s in reverse_external:
        base_url = reverse_external[rel_s]
    elif rel_s in reverse_same:
        base_url = reverse_same[rel_s]
    else:
        base_url = "https://openrockets.com/" + rel_s

    text = p.read_text(encoding="utf-8", errors="ignore")
    original = text
    text = rewrite_css_text(text, p, base_url)
    if text != original:
        p.write_text(text, encoding="utf-8")
        css_files_changed += 1

summary = {
    "vendor_migration": vendor_stats,
    "legacy_reference_files_changed": len(legacy_ref_changes),
    "pipeline_files_changed": pipeline_changes,
    "html_files_changed": html_files_changed,
    "html_refs_localized": html_refs_localized,
    "css_files_changed": css_files_changed,
    "css_refs_localized": css_refs_localized,
    "external_map_entries": len(external_map),
    "same_host_map_entries": len(same_map),
}

out = ROOT / ".github" / "recovery-audit" / "asset-integration.json"
out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
