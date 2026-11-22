#!/usr/bin/env python3
import hashlib
import json
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit, unquote

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / ".github" / "recovery-audit" / "internal-reference-audit.json"
EXCLUDE_TOP = {".git", ".github", "_vendor"}

ATTR_RE = re.compile(
    r'(?P<prefix>\b(?:href|src|poster|action|data-src|data-lazy-src|data-original|data-bg)\s*=\s*(?P<q>["\']))'
    r'(?P<url>[^"\']*)'
    r'(?P<suffix>(?P=q))',
    re.I,
)
SRCSET_RE = re.compile(
    r'(?P<prefix>\b(?:srcset|data-srcset)\s*=\s*(?P<q>["\']))'
    r'(?P<value>[^"\']*)'
    r'(?P<suffix>(?P=q))',
    re.I,
)
CSS_URL_RE = re.compile(
    r'url\(\s*(?P<q>["\']?)(?P<url>[^)"\']+)(?P=q)\s*\)',
    re.I,
)

def rel_dir(path: Path):
    d = path.parent.relative_to(ROOT).as_posix()
    return "." if d == "." else d

def normalize_fs_rel(value):
    value = unquote(value or "").replace("\\", "/")
    value = value.lstrip("/")
    if not value:
        return ""
    parts = []
    for part in PurePosixPath(value).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)

def file_or_route_exists(rel):
    rel = normalize_fs_rel(rel)
    if not rel:
        return True, "index.html", True
    p = ROOT / rel
    if p.is_file():
        return True, rel, False
    if p.is_dir() and (p / "index.html").is_file():
        return True, rel.rstrip("/") + "/", True
    if (ROOT / rel / "index.html").is_file():
        return True, rel.rstrip("/") + "/", True
    return False, rel, False

def relative_url(from_file: Path, target_rel: str, route=False, query="", fragment=""):
    start = rel_dir(from_file)
    target_rel = target_rel.rstrip("/") if route else target_rel
    if not target_rel:
        target_rel = "index.html"
    result = posixpath.relpath(target_rel, start=start)
    if route and not result.endswith("/"):
        result += "/"
    if result == "index.html" and from_file.parent == ROOT:
        result = "./"
    return urlunsplit(("", "", result, query, fragment))

def rewrite_one(raw, html_file: Path, unresolved):
    original = raw
    raw = raw.strip()
    if not raw or raw.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:")):
        return original

    # Fix malformed local path separators, but not schemes.
    if "://" not in raw and not raw.startswith("//"):
        raw = raw.replace("\\", "/")

    parts = urlsplit(raw)

    # External URLs stay external. Absolute openrockets.com URLs also stay absolute:
    # they are useful canonical/live references and do not need rewriting.
    if parts.scheme or parts.netloc:
        return raw

    path = parts.path
    if not path:
        return raw

    # Root-relative: make route-aware relative path only if recovered target exists.
    if path.startswith("/") and not path.startswith("//"):
        target = normalize_fs_rel(path)
        exists, target_rel, route = file_or_route_exists(target)
        if exists:
            return relative_url(
                html_file,
                target_rel,
                route=route or path.endswith("/"),
                query=parts.query,
                fragment=parts.fragment,
            )

        # Dynamic Cloudflare endpoints and true missing routes are reported, not guessed.
        unresolved.append({
            "file": html_file.relative_to(ROOT).as_posix(),
            "reference": raw,
            "resolved_candidate": target,
            "kind": "root-relative-missing",
        })
        return raw

    # Ordinary relative URL. If it already resolves to a recovered target, keep it.
    base_dir = html_file.parent.relative_to(ROOT).as_posix()
    combined = posixpath.normpath(posixpath.join(base_dir, path))
    exists, _, _ = file_or_route_exists(combined)
    if exists:
        return urlunsplit(("", "", path, parts.query, parts.fragment))

    # Common recovery/live-source bug: a nested page uses homepage-relative
    # "i/..." or "styles/..." even though the actual target is at repo root.
    root_candidate = normalize_fs_rel(path)
    exists_root, target_rel, route = file_or_route_exists(root_candidate)
    if exists_root:
        return relative_url(
            html_file,
            target_rel,
            route=route or path.endswith("/"),
            query=parts.query,
            fragment=parts.fragment,
        )

    # Static-looking unresolved references are significant.
    suffix = Path(path).suffix.lower()
    if suffix:
        unresolved.append({
            "file": html_file.relative_to(ROOT).as_posix(),
            "reference": raw,
            "resolved_candidate": combined,
            "root_candidate": root_candidate,
            "kind": "relative-static-missing",
        })

    return raw

def rewrite_html(path: Path, unresolved):
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    def attr_sub(m):
        return (
            m.group("prefix")
            + rewrite_one(m.group("url"), path, unresolved)
            + m.group("suffix")
        )

    text = ATTR_RE.sub(attr_sub, text)

    def srcset_sub(m):
        items = []
        for item in m.group("value").split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            rewritten = rewrite_one(bits[0], path, unresolved)
            items.append(" ".join([rewritten] + bits[1:]))
        return m.group("prefix") + ", ".join(items) + m.group("suffix")

    text = SRCSET_RE.sub(srcset_sub, text)

    def css_sub(m):
        raw = m.group("url")
        rewritten = rewrite_one(raw, path, unresolved)
        q = m.group("q")
        return f"url({q}{rewritten}{q})"

    text = CSS_URL_RE.sub(css_sub, text)

    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False

def rewrite_css(path: Path, unresolved):
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text

    def sub(m):
        raw = m.group("url").strip()
        if not raw or raw.startswith(("data:", "blob:", "#")):
            return m.group(0)
        if "://" in raw or raw.startswith("//"):
            return m.group(0)

        q = m.group("q")
        parts = urlsplit(raw)
        p = parts.path.replace("\\", "/")

        if p.startswith("/"):
            target = normalize_fs_rel(p)
            exists, target_rel, _ = file_or_route_exists(target)
            if exists:
                start = path.parent.relative_to(ROOT).as_posix()
                rel = posixpath.relpath(target_rel, start="." if start == "." else start)
                return f"url({q}{urlunsplit(('', '', rel, parts.query, parts.fragment))}{q})"
            unresolved.append({
                "file": path.relative_to(ROOT).as_posix(),
                "reference": raw,
                "resolved_candidate": target,
                "kind": "css-root-missing",
            })
            return m.group(0)

        base_dir = path.parent.relative_to(ROOT).as_posix()
        combined = posixpath.normpath(posixpath.join(base_dir, p))
        exists, _, _ = file_or_route_exists(combined)
        if not exists and Path(p).suffix:
            unresolved.append({
                "file": path.relative_to(ROOT).as_posix(),
                "reference": raw,
                "resolved_candidate": combined,
                "kind": "css-relative-missing",
            })
        return m.group(0)

    text = CSS_URL_RE.sub(sub, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False

def normalize_backslash_files():
    changes = []
    for path in list(ROOT.iterdir()):
        if not path.is_file() or "\\" not in path.name:
            continue
        normalized = ROOT / Path(*path.name.replace("\\", "/").split("/"))
        normalized.parent.mkdir(parents=True, exist_ok=True)

        if normalized.exists():
            if path.read_bytes() == normalized.read_bytes():
                path.unlink()
                changes.append({
                    "from": path.name,
                    "to": normalized.relative_to(ROOT).as_posix(),
                    "action": "removed duplicate malformed filename",
                })
            continue

        shutil.move(str(path), str(normalized))
        changes.append({
            "from": path.name,
            "to": normalized.relative_to(ROOT).as_posix(),
            "action": "moved malformed filename",
        })
    return changes

unresolved = []
changed_html = []
changed_css = []
backslash_changes = normalize_backslash_files()

for path in ROOT.rglob("*.html"):
    rel = path.relative_to(ROOT)
    if rel.parts and rel.parts[0] in EXCLUDE_TOP:
        continue
    if rewrite_html(path, unresolved):
        changed_html.append(rel.as_posix())

for path in ROOT.rglob("*.css"):
    rel = path.relative_to(ROOT)
    if rel.parts and rel.parts[0] in EXCLUDE_TOP:
        continue
    if rewrite_css(path, unresolved):
        changed_css.append(rel.as_posix())

# De-duplicate the unresolved report.
seen = set()
deduped = []
for item in unresolved:
    key = (item.get("file"), item.get("reference"), item.get("kind"))
    if key in seen:
        continue
    seen.add(key)
    deduped.append(item)

report = {
    "changed_html_count": len(changed_html),
    "changed_html": changed_html,
    "changed_css_count": len(changed_css),
    "changed_css": changed_css,
    "backslash_filename_changes": backslash_changes,
    "unresolved_count": len(deduped),
    "unresolved": deduped,
}

REPORT.parent.mkdir(parents=True, exist_ok=True)
REPORT.write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(json.dumps({
    "changed_html_count": report["changed_html_count"],
    "changed_css_count": report["changed_css_count"],
    "backslash_filename_change_count": len(backslash_changes),
    "unresolved_count": report["unresolved_count"],
}, indent=2))
