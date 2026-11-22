#!/usr/bin/env python3
import asyncio
import hashlib
import json
import mimetypes
import re
import shutil
import time
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse, urlunparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[2]
HOST = "openrockets.com"
START_URL = "https://openrockets.com/"
REPORT_DIR = ROOT / ".github" / "recovery-audit"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

MAX_PAGES = 150
FETCH_CONCURRENCY = 24
MAX_EXTERNAL_FILES = 6000
MAX_EXTERNAL_TOTAL = 500 * 1024 * 1024
MAX_SINGLE_FILE = 30 * 1024 * 1024
MAX_DEPENDENCY_FILES = 2500

SEEDS = [
    "https://openrockets.com/",
    "https://openrockets.com/join.html",
    "https://openrockets.com/team/",
    "https://openrockets.com/our-communities/",
    "https://openrockets.com/merch/",
    "https://openrockets.com/research/maple/v1",
    "https://openrockets.com/magazinesoftware/signup",
    "https://openrockets.com/opensource/",
    "https://openrockets.com/interkid",
]

SPECIAL_PROBES = [
    "/favicon.ico",
    "/apple-touch-icon.png",
    "/apple-touch-icon-precomposed.png",
    "/site.webmanifest",
    "/manifest.json",
    "/browserconfig.xml",
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap1.xml",
    "/wp-sitemap.xml",
]

STATIC_EXTS = {
    ".css", ".js", ".mjs", ".cjs", ".json", ".xml", ".txt", ".map",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".mov",
    ".pdf", ".zip", ".webmanifest",
}

ASSET_LIKE_EXTS = STATIC_EXTS - {".zip"}
TEXT_DEPS = {".css", ".js", ".mjs", ".cjs", ".svg", ".map"}
EXCLUDE_SCAN_TOP = {".git", ".github", "_vendor"}

page_queue = deque()
queued_pages = set()
visited_pages = set()
seen_resource_urls = set()
same_host_map = {}
external_map = {}
rejected = {}
failed = {}
special_probe_results = {}
removed_invalid_existing = []
cookie_check = {}
external_total = 0
write_lock = asyncio.Lock()
response_tasks = set()

def normalize_url(raw, base=START_URL):
    if not raw:
        return None
    raw = str(raw).strip()
    if not raw or raw.startswith(("#", "data:", "blob:", "javascript:", "mailto:", "tel:")):
        return None
    try:
        u = urljoin(base, raw.replace("\\/", "/"))
        p = urlparse(u)
        if p.scheme not in {"http", "https"}:
            return None
        host = (p.hostname or "").lower()
        if not host:
            return None
        return urlunparse(p._replace(fragment=""))
    except Exception:
        return None

def is_same_host(url):
    try:
        return (urlparse(url).hostname or "").lower() == HOST
    except Exception:
        return False

def looks_html(body):
    if not body:
        return False
    head = body[:4096].lstrip().lower()
    return (
        head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or b"<html" in head[:1500]
        or b"<head" in head[:1500] and b"<body" in head[:3000]
    )

def sha256_bytes(body):
    return hashlib.sha256(body).hexdigest()

def safe_rel_path(path_text):
    path_text = unquote(path_text or "").replace("\\", "/")
    rel = path_text.lstrip("/")
    if not rel:
        return None
    parts = PurePosixPath(rel).parts
    if any(part in {"", ".", ".."} for part in parts):
        return None
    return Path(*parts)

def page_path(url):
    p = urlparse(url)
    path = unquote(p.path or "/").replace("\\", "/")
    if path in {"", "/"}:
        return Path("index.html")
    rel = path.lstrip("/")
    if rel.endswith("/"):
        return Path(rel) / "index.html"
    suffix = Path(rel).suffix.lower()
    if suffix in {".html", ".htm"}:
        return Path(rel)
    if suffix:
        return Path(rel)
    return Path(rel) / "index.html"

def same_host_asset_path(url):
    return safe_rel_path(urlparse(url).path)

def external_path(url, content_type=""):
    p = urlparse(url)
    host = (p.hostname or "unknown-host").lower()
    raw_name = Path(unquote(p.path or "")).name or "resource"
    raw_name = re.sub(r"[^A-Za-z0-9._()\- ]+", "_", raw_name)[:150] or "resource"
    if "." not in raw_name:
        guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
        raw_name += guessed
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return Path("_vendor") / host / f"{digest}__{raw_name}"

def validate_body(path, body, content_type="", allow_html=False):
    ext = path.suffix.lower()
    ctype = (content_type or "").lower().split(";")[0].strip()

    if not body:
        return False, "empty body"
    if len(body) > MAX_SINGLE_FILE:
        return False, f"oversized: {len(body)} bytes"

    htmlish = looks_html(body)
    if htmlish and not allow_html and ext not in {".html", ".htm"}:
        return False, f"HTML fallback for {ext or 'extensionless'} ({ctype or 'no content-type'})"

    if ext == ".png" and not body.startswith(b"\x89PNG\r\n\x1a\n"):
        return False, "invalid PNG signature"
    if ext in {".jpg", ".jpeg"} and not body.startswith(b"\xff\xd8\xff"):
        return False, "invalid JPEG signature"
    if ext == ".gif" and not body.startswith((b"GIF87a", b"GIF89a")):
        return False, "invalid GIF signature"
    if ext == ".webp" and not (body.startswith(b"RIFF") and body[8:12] == b"WEBP"):
        return False, "invalid WEBP signature"
    if ext == ".ico" and not body.startswith(b"\x00\x00\x01\x00"):
        return False, "invalid ICO signature"
    if ext == ".pdf" and not body.startswith(b"%PDF-"):
        return False, "invalid PDF signature"
    if ext == ".woff" and not body.startswith(b"wOFF"):
        return False, "invalid WOFF signature"
    if ext == ".woff2" and not body.startswith(b"wOF2"):
        return False, "invalid WOFF2 signature"
    if ext in {".ttf", ".otf"} and not body.startswith((b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1")):
        return False, "invalid font signature"

    if ext == ".svg":
        text = body[:8192].decode("utf-8", errors="ignore").lower()
        if "<svg" not in text:
            return False, "invalid SVG body"

    if ext in {".json", ".webmanifest", ".map"}:
        try:
            json.loads(body.decode("utf-8", errors="strict"))
        except Exception:
            if ext != ".map":
                return False, f"invalid {ext} JSON"

    if ext == ".xml":
        try:
            ET.fromstring(body.decode("utf-8", errors="strict"))
        except Exception:
            return False, "invalid XML"

    if ext in {".css", ".js", ".mjs", ".cjs", ".txt"} and htmlish:
        return False, f"HTML fallback masquerading as {ext}"

    if ctype == "text/html" and ext in ASSET_LIKE_EXTS and ext not in {".html", ".htm"}:
        return False, f"text/html content-type for {ext}"

    return True, None

async def write_file(path, body):
    async with write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

def add_page(url):
    u = normalize_url(url)
    if not u or not is_same_host(u):
        return
    p = urlparse(u)
    decoded = unquote(p.path or "")
    if re.search(r"https?:/{1,2}", decoded, re.I) or "://" in decoded or "\\\\" in decoded:
        return
    ext = Path(decoded).suffix.lower()
    if ext in STATIC_EXTS and ext not in {".html", ".htm"}:
        return
    if u not in visited_pages and u not in queued_pages:
        queued_pages.add(u)
        page_queue.append(u)

def cleanup_existing_invalid_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if rel.parts and rel.parts[0] in EXCLUDE_SCAN_TOP:
            continue
        ext = path.suffix.lower()
        if ext not in ASSET_LIKE_EXTS:
            continue
        try:
            body = path.read_bytes()
        except Exception:
            continue
        ok, reason = validate_body(path, body, "", allow_html=False)
        if not ok and looks_html(body):
            removed_invalid_existing.append({
                "path": rel.as_posix(),
                "reason": reason,
                "sha256": sha256_bytes(body),
            })
            path.unlink()

async def save_same_host(url, body, content_type="", resource_type=""):
    u = normalize_url(url)
    if not u:
        return None

    is_document = resource_type == "document" or "text/html" in (content_type or "").lower()

    if is_document:
        path = ROOT / page_path(u)
        ok, reason = validate_body(path, body, content_type, allow_html=True)
        if not ok:
            rejected[u] = reason
            return None
    else:
        rel = same_host_asset_path(u)
        if rel is None:
            return None
        path = ROOT / rel
        ok, reason = validate_body(path, body, content_type, allow_html=False)
        if not ok:
            rejected[u] = reason
            return None

    if path.exists():
        try:
            if path.read_bytes() == body:
                same_host_map[u] = path.relative_to(ROOT).as_posix()
                return path
        except Exception:
            pass

    await write_file(path, body)
    same_host_map[u] = path.relative_to(ROOT).as_posix()
    return path

async def save_external(url, body, content_type="", resource_type=""):
    global external_total
    if len(external_map) >= MAX_EXTERNAL_FILES:
        return None
    if external_total + len(body) > MAX_EXTERNAL_TOTAL:
        return None

    path = ROOT / external_path(url, content_type)
    ok, reason = validate_body(
        path,
        body,
        content_type,
        allow_html=(resource_type == "document"),
    )
    if not ok:
        rejected[url] = reason
        return None

    if path.exists():
        try:
            if path.read_bytes() == body:
                external_map[url] = path.relative_to(ROOT).as_posix()
                return path
        except Exception:
            pass

    await write_file(path, body)
    external_total += len(body)
    external_map[url] = path.relative_to(ROOT).as_posix()
    return path

async def handle_response(response):
    try:
        u = normalize_url(response.url)
        if not u:
            return
        status = response.status
        if status < 200 or status >= 400:
            failed[u] = f"HTTP {status}"
            return

        headers = await response.all_headers()
        ctype = headers.get("content-type", "")
        resource_type = response.request.resource_type

        try:
            body = await response.body()
        except Exception as exc:
            failed[u] = f"body error: {type(exc).__name__}: {exc}"
            return

        if is_same_host(u):
            await save_same_host(u, body, ctype, resource_type)
        elif resource_type in {"stylesheet", "script", "image", "font", "media"}:
            await save_external(u, body, ctype, resource_type)

    except Exception as exc:
        failed[getattr(response, "url", "unknown")] = f"response handler: {type(exc).__name__}: {exc}"

async def direct_fetch(request_ctx, url, archive_external=True):
    u = normalize_url(url)
    if not u:
        return None
    if u in seen_resource_urls:
        return None
    seen_resource_urls.add(u)

    try:
        response = await request_ctx.get(
            u,
            timeout=10000,
            fail_on_status_code=False,
        )
        status = response.status
        ctype = response.headers.get("content-type", "")
        if status < 200 or status >= 400:
            failed[u] = f"HTTP {status}"
            return None
        body = await response.body()

        if is_same_host(u):
            return await save_same_host(u, body, ctype, "")
        if archive_external:
            return await save_external(u, body, ctype, "")
    except Exception as exc:
        failed[u] = f"fetch error: {type(exc).__name__}: {exc}"
    return None

async def fetch_many(request_ctx, urls, archive_external=True):
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def one(u):
        async with sem:
            return await direct_fetch(request_ctx, u, archive_external=archive_external)

    return await asyncio.gather(*(one(u) for u in urls), return_exceptions=True)

async def scroll_page(page):
    try:
        await page.evaluate("""async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          let lastHeight = -1;
          for (let i = 0; i < 30; i++) {
            window.scrollBy(0, Math.max(650, innerHeight * 0.85));
            await sleep(100);
            const h = document.documentElement.scrollHeight;
            if (window.scrollY + innerHeight >= h - 5 && h === lastHeight) break;
            lastHeight = h;
          }
          window.scrollTo(0, 0);
        }""")
    except Exception:
        pass

async def collect_dom(page):
    try:
        data = await page.evaluate("""() => {
          const pages = [];
          const assets = [];
          const addAsset = v => { if (v) assets.push(v); };

          document.querySelectorAll('a[href]').forEach(a => pages.push(a.href));

          document.querySelectorAll('*').forEach(el => {
            for (const a of ['src','poster','data-src','data-lazy-src','data-original','data-bg']) {
              if (el.hasAttribute && el.hasAttribute(a)) addAsset(el.getAttribute(a));
            }

            if (el.tagName === 'LINK' && el.hasAttribute('href')) {
              const rel = (el.getAttribute('rel') || '').toLowerCase();
              if (/(stylesheet|icon|manifest|preload|modulepreload|prefetch)/.test(rel)) {
                addAsset(el.getAttribute('href'));
              }
            }

            const ss = el.getAttribute && (el.getAttribute('srcset') || el.getAttribute('data-srcset'));
            if (ss) {
              ss.split(',').forEach(x => addAsset(x.trim().split(/\\s+/)[0]));
            }

            const style = el.getAttribute && el.getAttribute('style');
            if (style) {
              for (const m of style.matchAll(/url\\(\\s*['"]?([^)'"]+)['"]?\\s*\\)/gi)) {
                addAsset(m[1]);
              }
            }
          });

          return { pages, assets };
        }""")
        return data
    except Exception:
        return {"pages": [], "assets": []}

async def special_probes(request_ctx):
    for rel in SPECIAL_PROBES:
        url = urljoin(START_URL, rel)
        try:
            response = await request_ctx.get(url, timeout=10000, fail_on_status_code=False)
            ctype = response.headers.get("content-type", "")
            body = await response.body()
            target = ROOT / rel.lstrip("/")
            ok, reason = validate_body(target, body, ctype, allow_html=False)

            special_probe_results[rel] = {
                "status": response.status,
                "content_type": ctype,
                "bytes": len(body),
                "valid": bool(response.status >= 200 and response.status < 400 and ok),
                "reason": reason,
            }

            if 200 <= response.status < 400 and ok:
                await write_file(target, body)
                same_host_map[url] = target.relative_to(ROOT).as_posix()
            else:
                if target.exists():
                    try:
                        existing = target.read_bytes()
                        existing_ok, _ = validate_body(target, existing, "", allow_html=False)
                        if not existing_ok:
                            target.unlink()
                    except Exception:
                        pass
        except Exception as exc:
            special_probe_results[rel] = {
                "status": None,
                "valid": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }

async def dependency_fixpoint(request_ctx):
    reverse = {}
    for url, rel in same_host_map.items():
        reverse[rel] = url
    for url, rel in external_map.items():
        reverse[rel] = url

    queue = deque()
    for rel, source_url in reverse.items():
        if Path(rel).suffix.lower() in TEXT_DEPS:
            queue.append((source_url, ROOT / rel))

    scanned = set()
    css_url_re = re.compile(r"url\\(\\s*(['\"]?)([^)'\"\\s]+)\\1\\s*\\)", re.I)
    import_re = re.compile(r"@import\\s+(?:url\\()?\\s*['\"]?([^'\"\\)\\s;]+)", re.I)
    sm_re = re.compile(r"(?://[#@]\\s*sourceMappingURL=|/\\*[#@]\\s*sourceMappingURL=)([^\\s*]+)", re.I)

    count = 0
    while queue and count < MAX_DEPENDENCY_FILES:
        batch = []
        while queue and len(batch) < 40 and count < MAX_DEPENDENCY_FILES:
            source_url, path = queue.popleft()
            key = path.as_posix()
            if key in scanned or not path.is_file():
                continue
            scanned.add(key)
            batch.append((source_url, path))
            count += 1

        candidates = set()
        for source_url, path in batch:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            raw_urls = []
            if path.suffix.lower() == ".css":
                raw_urls.extend(m.group(2) for m in css_url_re.finditer(text))
                raw_urls.extend(m.group(1) for m in import_re.finditer(text))
            raw_urls.extend(m.group(1).strip().strip("'\"") for m in sm_re.finditer(text))

            for raw in raw_urls:
                u = normalize_url(raw, source_url)
                if u and u not in seen_resource_urls:
                    candidates.add(u)

        if not candidates:
            continue

        before_same = set(same_host_map)
        before_ext = set(external_map)
        await fetch_many(request_ctx, sorted(candidates), archive_external=True)

        for u in candidates:
            rel = None
            if u in same_host_map and u not in before_same:
                rel = same_host_map[u]
            elif u in external_map and u not in before_ext:
                rel = external_map[u]
            if rel and Path(rel).suffix.lower() in TEXT_DEPS:
                queue.append((u, ROOT / rel))

async def run():
    cleanup_existing_invalid_files()

    for seed in SEEDS:
        add_page(seed)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            ignore_https_errors=True,
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        )
        request_ctx = context.request

        await special_probes(request_ctx)

        page = await context.new_page()

        def on_response(response):
            task = asyncio.create_task(handle_response(response))
            response_tasks.add(task)
            task.add_done_callback(response_tasks.discard)

        page.on("response", on_response)

        page_no = 0
        while page_queue and page_no < MAX_PAGES:
            url = page_queue.popleft()
            queued_pages.discard(url)
            if url in visited_pages:
                continue
            visited_pages.add(url)
            page_no += 1
            print(f"[PAGE {page_no}] {url}", flush=True)

            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=35000,
                )
                if response is None:
                    failed[url] = "no navigation response"
                    continue

                try:
                    await page.wait_for_load_state("networkidle", timeout=7000)
                except Exception:
                    pass

                await scroll_page(page)
                await page.wait_for_timeout(500)

                dom = await collect_dom(page)

                for href in dom["pages"]:
                    u = normalize_url(href, page.url)
                    if u and is_same_host(u):
                        add_page(u)

                direct_assets = []
                seen_local = set()
                for raw in dom["assets"]:
                    u = normalize_url(raw, page.url)
                    if not u or u in seen_local:
                        continue
                    seen_local.add(u)

                    p = urlparse(u)
                    ext = Path(unquote(p.path or "")).suffix.lower()

                    if is_same_host(u):
                        if ext in STATIC_EXTS:
                            direct_assets.append(u)
                    else:
                        if ext in STATIC_EXTS:
                            direct_assets.append(u)

                if direct_assets:
                    await fetch_many(request_ctx, direct_assets, archive_external=True)

                if url == START_URL:
                    banner = page.locator(".termsfeed-com---nb")
                    visible = False
                    clicked = False
                    closed = False
                    try:
                        if await banner.count():
                            visible = await banner.first.is_visible()
                    except Exception:
                        pass

                    if visible:
                        for selector in [
                            ".cc-nb-reject",
                            ".cc-nb-okagree",
                            'button:has-text("Reject")',
                            'button:has-text("Accept")',
                            'button:has-text("Agree")',
                        ]:
                            loc = page.locator(selector)
                            try:
                                if await loc.count() and await loc.first.is_visible():
                                    await loc.first.click(timeout=3000)
                                    clicked = True
                                    break
                            except Exception:
                                pass

                        if clicked:
                            await page.wait_for_timeout(700)
                            try:
                                closed = not await banner.first.is_visible() if await banner.count() else True
                            except Exception:
                                closed = True

                    cookie_check.update({
                        "visible_before": visible,
                        "clicked": clicked,
                        "closed_after_click": closed,
                    })

            except PlaywrightTimeoutError as exc:
                failed[url] = f"navigation timeout: {exc}"
            except Exception as exc:
                failed[url] = f"navigation error: {type(exc).__name__}: {exc}"

        if response_tasks:
            await asyncio.gather(*list(response_tasks), return_exceptions=True)

        await dependency_fixpoint(request_ctx)

        await context.close()
        await browser.close()

    # Final invalid-file scan: do not permit HTML fallbacks under asset extensions.
    remaining_invalid = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if rel.parts and rel.parts[0] in {".git", ".github", "_vendor"}:
            continue
        if path.suffix.lower() not in ASSET_LIKE_EXTS:
            continue
        try:
            body = path.read_bytes()
        except Exception:
            continue
        ok, reason = validate_body(path, body, "", allow_html=False)
        if not ok and looks_html(body):
            remaining_invalid.append({
                "path": rel.as_posix(),
                "reason": reason,
            })

    # Validate favicon actually referenced by homepage.
    favicon = {"href": None, "local_path": None, "valid": False}
    index = ROOT / "index.html"
    if index.is_file():
        source = index.read_text(encoding="utf-8", errors="ignore")
        m = re.search(
            r'<link[^>]+rel=["\'][^"\']*(?:icon|shortcut icon)[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
            source,
            re.I,
        )
        if m:
            href = m.group(1)
            favicon["href"] = href
            u = normalize_url(href, START_URL)
            if u and is_same_host(u):
                rel = same_host_asset_path(u)
                if rel:
                    p = ROOT / rel
                    favicon["local_path"] = rel.as_posix()
                    if p.is_file():
                        ok, _ = validate_body(p, p.read_bytes(), "", allow_html=False)
                        favicon["valid"] = ok

    report = {
        "generated_at_unix": int(time.time()),
        "visited_page_count": len(visited_pages),
        "visited_pages": sorted(visited_pages),
        "same_host_saved_count": len(same_host_map),
        "external_archived_count": len(external_map),
        "external_archived_bytes": external_total,
        "removed_invalid_existing_count": len(removed_invalid_existing),
        "removed_invalid_existing": removed_invalid_existing,
        "special_probes": special_probe_results,
        "cookie_check": cookie_check,
        "favicon": favicon,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "failed_count": len(failed),
        "failed": failed,
        "remaining_html_disguised_assets": remaining_invalid,
        "same_host_map": same_host_map,
        "external_map": external_map,
    }

    (REPORT_DIR / "authoritative-recovery-sync.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps({
        "visited_page_count": report["visited_page_count"],
        "same_host_saved_count": report["same_host_saved_count"],
        "external_archived_count": report["external_archived_count"],
        "removed_invalid_existing_count": report["removed_invalid_existing_count"],
        "remaining_html_disguised_assets": len(remaining_invalid),
        "cookie_check": cookie_check,
        "favicon": favicon,
        "rejected_count": report["rejected_count"],
        "failed_count": report["failed_count"],
    }, indent=2), flush=True)

    if remaining_invalid:
        raise SystemExit(
            f"FAIL: {len(remaining_invalid)} HTML fallback file(s) still masquerade as assets"
        )

    if not index.is_file():
        raise SystemExit("FAIL: index.html missing after live sync")

    if favicon["href"] and not favicon["valid"]:
        raise SystemExit(f"FAIL: homepage favicon is not a valid recovered local file: {favicon}")

    if cookie_check.get("visible_before") and not cookie_check.get("closed_after_click"):
        raise SystemExit("FAIL: cookie banner was visible but did not close")

asyncio.run(run())
