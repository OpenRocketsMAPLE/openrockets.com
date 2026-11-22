#!/usr/bin/env python3
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "recovery_snapshot"
PAGES = RECOVERY / "pages"
MANIFEST = RECOVERY / "metadata" / "url_to_saved_file.json"

if not PAGES.is_dir():
    raise SystemExit("recovery_snapshot/pages is missing")
if not MANIFEST.is_file():
    raise SystemExit("recovery manifest is missing")

def same_bytes(a: Path, b: Path) -> bool:
    if not a.is_file() or not b.is_file():
        return False
    if a.stat().st_size != b.stat().st_size:
        return False
    def digest(p):
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.digest()
    return digest(a) == digest(b)

def safe_relative_url_path(url: str):
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() != "openrockets.com":
        return None

    raw = unquote(parsed.path or "/")
    if raw in ("", "/"):
        return None

    rel = raw.lstrip("/")
    if not rel or rel.endswith("/"):
        return None

    parts = PurePosixPath(rel).parts
    if any(p in ("", ".", "..") for p in parts):
        return None

    if rel.startswith("cdn-cgi/"):
        # Cloudflare runtime infrastructure is not source code for this site.
        return None

    return Path(*parts)

print("Materializing rendered route files at repository root...")

# 1) Route/page tree: index.html, join.html, team/, merch/, research/, etc.
for item in PAGES.iterdir():
    destination = ROOT / item.name

    if destination.exists():
        if destination.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        elif item.is_file() and not same_bytes(item, destination):
            shutil.copy2(item, destination)
    else:
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

copied = 0
skipped_conflicts = 0

print("Reconstructing original openrockets.com asset paths...")

# 2) Restore same-host public files to their original URL paths.
#    External CDN files remain external references and are not dumped into root.
for url, saved_rel in manifest.items():
    rel_url_path = safe_relative_url_path(url)
    if rel_url_path is None:
        continue

    source = RECOVERY / saved_rel
    if not source.is_file():
        continue

    destination = ROOT / rel_url_path

    # Do not replace route directories such as team/, merch/, research/.
    if destination.exists() and destination.is_dir():
        skipped_conflicts += 1
        continue

    # Extensionless network endpoints are not useful as static source files.
    if destination.suffix == "" and destination.name not in {
        "robots.txt",
        "sitemap.xml",
        "sitemap_index.xml",
        "sitemap-index.xml",
        "sitemap1.xml",
        "wp-sitemap.xml",
    }:
        continue

    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        if same_bytes(source, destination):
            continue

        # Prefer the rendered page tree if there is a collision.
        try:
            destination.relative_to(PAGES)
        except ValueError:
            pass

        # If a page with this exact repository path was already materialized,
        # preserve the rendered page rather than a browser-response duplicate.
        page_equivalent = PAGES / rel_url_path
        if page_equivalent.exists():
            skipped_conflicts += 1
            continue

    shutil.copy2(source, destination)
    copied += 1

# 3) Clean recovery-only wrappers from current main branch.
print("Cleaning recovery-only wrapper files...")

if RECOVERY.exists():
    shutil.rmtree(RECOVERY)

preview_script = ROOT / "scripts" / "build_pages_preview.py"
if preview_script.exists():
    preview_script.unlink()

scripts_dir = ROOT / "scripts"
if scripts_dir.exists() and not any(scripts_dir.iterdir()):
    scripts_dir.rmdir()

import_workflow = ROOT / ".github" / "workflows" / "import-recovery.yml"
if import_workflow.exists():
    import_workflow.unlink()

# This one-shot workflow deletes itself from the resulting commit.
restructure_workflow = ROOT / ".github" / "workflows" / "restructure-recovery.yml"
if restructure_workflow.exists():
    restructure_workflow.unlink()

# This script is also one-shot.
this_script = Path(__file__)
if this_script.exists():
    this_script.unlink()

scripts_dir = ROOT / "scripts"
if scripts_dir.exists() and not any(scripts_dir.iterdir()):
    scripts_dir.rmdir()

print(f"Reconstructed {copied} same-host public files.")
print(f"Skipped {skipped_conflicts} path conflicts safely.")
print("Repository root is now the website root.")
