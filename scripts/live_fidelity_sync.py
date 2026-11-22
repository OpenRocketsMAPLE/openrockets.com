#!/usr/bin/env python3
import asyncio
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlparse, urlunparse, unquote

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parents[1]
HOST = "openrockets.com"
START_URL = "https://openrockets.com/"
MAX_PAGES = 250
MAX_EXTERNAL_RESOURCES = 5000
MAX_SINGLE_RESOURCE_BYTES = 30 * 1024 * 1024
MAX_EXTERNAL_TOTAL_BYTES = 350 * 1024 * 1024

AUDIT_DIR = ROOT / ".github" / "recovery-audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

STATIC_EXTS = {
    ".css",".js",".mjs",".cjs",".json",".xml",".txt",".map",
    ".png",".jpg",".jpeg",".webp",".gif",".svg",".ico",".avif",
    ".woff",".woff2",".ttf",".otf",".eot",
    ".mp3",".wav",".ogg",".mp4",".webm",".mov",".pdf",".zip"
}
TEXT_EXTS = {".html",".htm",".css",".js",".mjs",".cjs",".json",".xml",".txt",".svg",".map"}

pages_seen = set()
pages_queued = set()
page_queue = deque()
resources_seen = set()
saved_urls = {}
failed_urls = {}
external_saved = {}
external_total_bytes = 0
response_tasks = set()
write_lock = asyncio.Lock()

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def normalize_url(raw: str, base: str = START_URL):
    if not raw:
        return None
    try:
        raw = raw.strip()
        if raw.startswith(("data:","blob:","javascript:","mailto:","tel:","#")):
            return None
        u = urljoin(base, raw)
        p = urlparse(u)
        if p.scheme not in ("http","https"):
            return None
        host = (p.hostname or "").lower()
        if not host:
            return None
        clean = p._replace(fragment="")
        return urlunparse(clean)
    except Exception:
        return None

def is_exact_host(url: str) -> bool:
    try:
        return (urlparse(url).hostname or "").lower() == HOST
    except Exception:
        return False

def looks_like_static_path(url: str) -> bool:
    try:
        path = unquote(urlparse(url).path or "")
        ext = Path(path).suffix.lower()
        return ext in STATIC_EXTS
    except Exception:
        return False

def route_path_for_url(url: str) -> Path:
    p = urlparse(url)
    raw = unquote(p.path or "/")
    if raw in ("", "/"):
        return Path("index.html")
    rel = raw.lstrip("/")
    if rel.endswith("/"):
        return Path(rel) / "index.html"
    suffix = Path(rel).suffix.lower()
    if suffix in {".html",".htm"}:
        return Path(rel)
    if suffix:
        return Path(rel)
    return Path(rel) / "index.html"

def safe_asset_path_for_same_host(url: str):
    p = urlparse(url)
    if (p.hostname or "").lower() != HOST:
        return None
    raw = unquote(p.path or "")
    rel = raw.lstrip("/")
    if not rel or rel.endswith("/"):
        return None
    parts = PurePosixPath(rel).parts
    if any(part in ("",".","..") for part in parts):
        return None
    return Path(*parts)

def safe_external_archive_path(url: str, content_type: str = ""):
    p = urlparse(url)
    host = (p.hostname or "unknown-host").lower()
    raw_name = Path(unquote(p.path or "")).name or "index"
    raw_name = re.sub(r"[^A-Za-z0-9._()\- ]+", "_", raw_name)[:140] or "resource"
    if "." not in raw_name:
        guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
        if guessed:
            raw_name += guessed
    prefix = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return Path("_vendor") / host / f"{prefix}__{raw_name}"

def add_page(url: str):
    u = normalize_url(url)
    if not u or not is_exact_host(u) or looks_like_static_path(u):
        return
    # Avoid recursive crawler junk.
    decoded = unquote(urlparse(u).path or "")
    if re.search(r"https?:/{1,2}", decoded, re.I) or "://" in decoded or "\\" in decoded:
        return
    if u not in pages_seen and u not in pages_queued:
        pages_queued.add(u)
        page_queue.append(u)

async def write_bytes(path: Path, data: bytes):
    async with write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

async def save_response(response):
    global external_total_bytes
    try:
        url = normalize_url(response.url)
        if not url or url in resources_seen:
            return
        resources_seen.add(url)

        req = response.request
        status = response.status
        if status < 200 or status >= 400:
            failed_urls[url] = f"HTTP {status}"
            return

        headers = await response.all_headers()
        content_type = headers.get("content-type","")
        resource_type = req.resource_type

        try:
            body = await response.body()
        except Exception as e:
            failed_urls[url] = f"body: {type(e).__name__}: {e}"
            return

        if not body:
            return
        if len(body) > MAX_SINGLE_RESOURCE_BYTES:
            failed_urls[url] = f"skipped oversized resource: {len(body)} bytes"
            return

        if is_exact_host(url):
            if resource_type == "document" or "text/html" in content_type.lower():
                path = ROOT / route_path_for_url(url)
            else:
                rel = safe_asset_path_for_same_host(url)
                if rel is None:
                    return
                path = ROOT / rel

            # Querystring variants normally map to the same deployed file. Preserve the
            # first successful body at the canonical path, but record all URLs.
            if path.exists():
                existing = path.read_bytes()
                if existing != body and sha256_bytes(existing) != sha256_bytes(body):
                    # Prefer real document source over prior rendered snapshots.
                    if resource_type != "document" and "text/html" not in content_type.lower():
                        qhash = hashlib.sha256(url.encode()).hexdigest()[:10]
                        path = path.with_name(path.stem + f"__q_{qhash}" + path.suffix)

            await write_bytes(path, body)
            saved_urls[url] = str(path.relative_to(ROOT))

        else:
            if len(external_saved) >= MAX_EXTERNAL_RESOURCES:
                return
            if external_total_bytes + len(body) > MAX_EXTERNAL_TOTAL_BYTES:
                return
            path = ROOT / safe_external_archive_path(url, content_type)
            await write_bytes(path, body)
            external_total_bytes += len(body)
            external_saved[url] = str(path.relative_to(ROOT))

    except Exception as e:
        failed_urls[getattr(response, "url", "unknown")] = f"response handler: {type(e).__name__}: {e}"

async def fetch_url(request_ctx, url: str, archive_external=True):
    global external_total_bytes
    u = normalize_url(url)
    if not u or u in resources_seen:
        return
    resources_seen.add(u)
    try:
        r = await request_ctx.get(u, timeout=30000, fail_on_status_code=False)
        if r.status < 200 or r.status >= 400:
            failed_urls[u] = f"HTTP {r.status}"
            return
        body = await r.body()
        if not body or len(body) > MAX_SINGLE_RESOURCE_BYTES:
            if body:
                failed_urls[u] = f"skipped oversized resource: {len(body)} bytes"
            return
        ctype = r.headers.get("content-type","")

        if is_exact_host(u):
            rel = safe_asset_path_for_same_host(u)
            if rel is None:
                return
            path = ROOT / rel
            if path.exists() and path.read_bytes() != body:
                qhash = hashlib.sha256(u.encode()).hexdigest()[:10]
                path = path.with_name(path.stem + f"__q_{qhash}" + path.suffix)
            await write_bytes(path, body)
            saved_urls[u] = str(path.relative_to(ROOT))
        elif archive_external:
            if len(external_saved) >= MAX_EXTERNAL_RESOURCES:
                return
            if external_total_bytes + len(body) > MAX_EXTERNAL_TOTAL_BYTES:
                return
            path = ROOT / safe_external_archive_path(u, ctype)
            await write_bytes(path, body)
            external_total_bytes += len(body)
            external_saved[u] = str(path.relative_to(ROOT))
    except Exception as e:
        failed_urls[u] = f"fetch: {type(e).__name__}: {e}"

def extract_urls_from_srcset(value: str):
    out = []
    for item in (value or "").split(","):
        item = item.strip()
        if item:
            out.append(item.split()[0])
    return out

async def collect_dom_urls(page):
    js = """() => {
      const out = [];
      const add = (v) => { if (v) out.push(v); };
      for (const el of document.querySelectorAll('*')) {
        for (const attr of ['src','href','poster','data-src','data-lazy-src','data-original']) {
          if (el.hasAttribute && el.hasAttribute(attr)) add(el.getAttribute(attr));
        }
        if (el.getAttribute) {
          const ss = el.getAttribute('srcset') || el.getAttribute('data-srcset');
          if (ss) out.push(...ss.split(',').map(x => x.trim().split(/\s+/)[0]));
        }
      }
      return out;
    }"""
    try:
        vals = await page.evaluate(js)
    except Exception:
        return []
    out = []
    base = page.url
    for raw in vals:
        u = normalize_url(raw, base)
        if u:
            out.append(u)
    return out

async def full_scroll(page):
    try:
        await page.evaluate("""async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          let last = -1;
          for (let i = 0; i < 25; i++) {
            window.scrollBy(0, Math.max(500, window.innerHeight * 0.8));
            await sleep(80);
            const y = window.scrollY;
            if (y === last) break;
            last = y;
          }
          window.scrollTo(0, 0);
        }""")
    except Exception:
        pass

async def hover_interactives(page):
    try:
        loc = page.locator("a,button,[role=button]")
        count = min(await loc.count(), 30)
        for i in range(count):
            try:
                await loc.nth(i).hover(timeout=120)
            except Exception:
                pass
    except Exception:
        pass

async def collect_sitemaps(request_ctx):
    candidates = [
        "https://openrockets.com/sitemap.xml",
        "https://openrockets.com/sitemap_index.xml",
        "https://openrockets.com/sitemap-index.xml",
        "https://openrockets.com/sitemap1.xml",
        "https://openrockets.com/wp-sitemap.xml",
    ]
    seen = set()
    queue = deque(candidates)
    while queue and len(seen) < 50:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        try:
            r = await request_ctx.get(url, timeout=20000, fail_on_status_code=False)
            if r.status < 200 or r.status >= 400:
                continue
            body = await r.body()
            if body:
                rel = safe_asset_path_for_same_host(url)
                if rel:
                    await write_bytes(ROOT / rel, body)
                    saved_urls[url] = str(rel)
            txt = body.decode("utf-8", errors="ignore")
            root = ET.fromstring(txt)
            locs = [n.text.strip() for n in root.iter() if n.tag.endswith("loc") and n.text]
            for loc in locs:
                u = normalize_url(loc)
                if not u:
                    continue
                if "sitemap" in (urlparse(u).path or "").lower() and u not in seen:
                    queue.append(u)
                elif is_exact_host(u):
                    add_page(u)
        except Exception:
            continue

async def fetch_explicit_well_known(request_ctx):
    paths = [
        "/favicon.ico",
        "/apple-touch-icon.png",
        "/apple-touch-icon-precomposed.png",
        "/site.webmanifest",
        "/manifest.json",
        "/browserconfig.xml",
        "/robots.txt",
    ]
    for p in paths:
        await fetch_url(request_ctx, urljoin(START_URL, p), archive_external=False)

async def crawl():
    add_page(START_URL)

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
            viewport={"width": 1440, "height": 1050},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
            ignore_https_errors=True,
        )
        request_ctx = context.request

        await collect_sitemaps(request_ctx)
        await fetch_explicit_well_known(request_ctx)

        page = await context.new_page()

        def on_response(resp):
            task = asyncio.create_task(save_response(resp))
            response_tasks.add(task)
            task.add_done_callback(response_tasks.discard)

        page.on("response", on_response)

        page_no = 0
        while page_queue and page_no < MAX_PAGES:
            url = page_queue.popleft()
            pages_queued.discard(url)
            if url in pages_seen:
                continue
            pages_seen.add(url)
            page_no += 1
            print(f"[PAGE {page_no}] {url}", flush=True)

            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if resp is None:
                    failed_urls[url] = "no navigation response"
                    continue

                try:
                    await page.wait_for_load_state("networkidle", timeout=4000)
                except Exception:
                    pass

                await full_scroll(page)
                await hover_interactives(page)
                await page.wait_for_timeout(800)

                final_url = normalize_url(page.url)
                if final_url and is_exact_host(final_url):
                    add_page(final_url)

                # Navigation comes ONLY from real anchors.
                try:
                    hrefs = await page.locator("a[href]").evaluate_all(
                        "els => els.map(e => e.href).filter(Boolean)"
                    )
                    for href in hrefs:
                        u = normalize_url(href, page.url)
                        if u and is_exact_host(u):
                            add_page(u)
                except Exception:
                    pass

                # Fetch every explicit DOM asset reference, not only the viewport-selected one.
                dom_urls = await collect_dom_urls(page)
                for asset_url in dom_urls:
                    # Browser response capture already handles dynamically loaded
                    # extensionless scripts/APIs. Explicit DOM fetching is reserved
                    # for actual static resources so outbound navigation URLs do not
                    # turn into slow external page downloads.
                    if not looks_like_static_path(asset_url):
                        continue
                    await fetch_url(request_ctx, asset_url, archive_external=True)

            except PlaywrightTimeoutError as e:
                failed_urls[url] = f"navigation timeout: {e}"
            except Exception as e:
                failed_urls[url] = f"navigation: {type(e).__name__}: {e}"

        if response_tasks:
            await asyncio.gather(*list(response_tasks), return_exceptions=True)

        # Second-order dependency discovery from saved CSS/JS/source files.
        pending = deque()
        for url, rel in list(saved_urls.items()):
            if Path(rel).suffix.lower() in {".css",".js",".mjs",".cjs",".html",".htm",".svg"}:
                pending.append((url, ROOT / rel))
        for url, rel in list(external_saved.items()):
            if Path(rel).suffix.lower() in {".css",".js",".mjs",".cjs",".html",".htm",".svg"}:
                pending.append((url, ROOT / rel))

        scanned_files = set()
        css_url_re = re.compile(r"url\(\s*(['\"]?)([^)'\"\s]+)\1\s*\)", re.I)
        sm_re = re.compile(r"(?://[#@]\s*sourceMappingURL=|/\*[#@]\s*sourceMappingURL=)([^\s*]+)", re.I)
        quoted_abs_re = re.compile(r"['\"](https?://[^'\"\s<>]+)['\"]", re.I)

        rounds = 0
        while pending and rounds < 8000:
            base_url, path = pending.popleft()
            rounds += 1
            key = str(path)
            if key in scanned_files or not path.is_file():
                continue
            scanned_files.add(key)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            found = set()
            for m in css_url_re.finditer(text):
                found.add(m.group(2))
            for m in sm_re.finditer(text):
                found.add(m.group(1).strip().strip("'\""))
            for m in quoted_abs_re.finditer(text):
                found.add(m.group(1))
            for raw in found:
                u = normalize_url(raw, base_url)
                if not u:
                    continue
                before_local = set(saved_urls)
                before_ext = set(external_saved)
                await fetch_url(request_ctx, u, archive_external=True)
                if u in saved_urls and u not in before_local:
                    p = ROOT / saved_urls[u]
                    if p.suffix.lower() in {".css",".js",".mjs",".cjs",".html",".htm",".svg"}:
                        pending.append((u,p))
                if u in external_saved and u not in before_ext:
                    p = ROOT / external_saved[u]
                    if p.suffix.lower() in {".css",".js",".mjs",".cjs",".html",".htm",".svg"}:
                        pending.append((u,p))

        await context.close()
        await browser.close()

asyncio.run(crawl())

# Validate the homepage is SOURCE HTML, not a frozen runtime DOM.
index = ROOT / "index.html"
if not index.exists():
    raise SystemExit("FAIL: live crawl did not recover index.html")

index_text = index.read_text(encoding="utf-8", errors="ignore")

cookie_source_ok = (
    "cookieconsent.run(" in index_text
    and "www.termsfeed.com/public/cookie-consent" in index_text
)
frozen_cookie_dom = "termsfeed-com---nb-title" in index_text or 'class="termsfeed-com---nb' in index_text

icon_match = re.search(
    r'<link[^>]+rel=["\'][^"\']*icon[^"\']*["\'][^>]+href=["\']([^"\']+)["\']',
    index_text,
    re.I,
)
favicon_ok = False
favicon_href = None
favicon_local = None
if icon_match:
    favicon_href = icon_match.group(1)
    favicon_url = normalize_url(favicon_href, START_URL)
    if favicon_url and is_exact_host(favicon_url):
        rel = safe_asset_path_for_same_host(favicon_url)
        if rel:
            favicon_local = str(rel)
            favicon_ok = (ROOT / rel).is_file()
    elif favicon_url:
        favicon_ok = favicon_url in external_saved

report = {
    "generated_at_unix": int(time.time()),
    "start_url": START_URL,
    "pages_seen": sorted(pages_seen),
    "page_count": len(pages_seen),
    "same_host_saved_count": len(saved_urls),
    "external_archived_count": len(external_saved),
    "external_archived_bytes": external_total_bytes,
    "failed_count": len(failed_urls),
    "failed_urls": failed_urls,
    "cookie_source_initialization_present": cookie_source_ok,
    "frozen_termsfeed_runtime_dom_present": frozen_cookie_dom,
    "favicon_href": favicon_href,
    "favicon_local_path": favicon_local,
    "favicon_local_file_present": favicon_ok,
    "same_host_url_map": saved_urls,
    "external_archive_map": external_saved,
}
(AUDIT_DIR / "live-fidelity-sync.json").write_text(
    json.dumps(report, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(json.dumps({
    "page_count": report["page_count"],
    "same_host_saved_count": report["same_host_saved_count"],
    "external_archived_count": report["external_archived_count"],
    "external_archived_bytes": report["external_archived_bytes"],
    "failed_count": report["failed_count"],
    "cookie_source_initialization_present": cookie_source_ok,
    "frozen_termsfeed_runtime_dom_present": frozen_cookie_dom,
    "favicon_href": favicon_href,
    "favicon_local_file_present": favicon_ok,
}, indent=2), flush=True)

if not cookie_source_ok:
    raise SystemExit("FAIL: TermsFeed cookie consent source initialization was not recovered")
if frozen_cookie_dom:
    raise SystemExit("FAIL: index.html still contains frozen TermsFeed runtime DOM")
if favicon_href and not favicon_ok:
    raise SystemExit(f"FAIL: favicon reference exists but local file is missing: {favicon_href}")
