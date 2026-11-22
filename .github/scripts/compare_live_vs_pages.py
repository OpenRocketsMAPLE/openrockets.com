#!/usr/bin/env python3
import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

LIVE = "https://openrockets.com/"
RECOVERED = "https://openrocketsmaple.github.io/openrockets.com/"
OUT = Path(".github/recovery-audit/live-vs-pages")
OUT.mkdir(parents=True, exist_ok=True)

ROUTES = [
    "",
    "team/",
    "our-communities/",
    "merch/",
    "join.html",
    "research/maple/v1/",
    "magazinesoftware/signup/",
]

KEY_SELECTORS = [
    "html",
    "body",
    "#main-header",
    "header",
    "main",
    "h1",
    "h2",
    ".hero-section",
    ".hero-section__title",
    ".hds-button",
    ".home-banner",
    ".partner-feature-media",
    ".maple-live-section-title",
    "footer",
]

STYLE_KEYS = [
    "display","position","width","height","maxWidth","minHeight",
    "marginTop","marginRight","marginBottom","marginLeft",
    "paddingTop","paddingRight","paddingBottom","paddingLeft",
    "fontFamily","fontSize","fontWeight","lineHeight","letterSpacing",
    "color","backgroundColor","backgroundImage","borderRadius",
    "borderTopWidth","borderRightWidth","borderBottomWidth","borderLeftWidth",
    "boxShadow","opacity","transform","overflow","gap","flexDirection",
    "justifyContent","alignItems","gridTemplateColumns",
]

STATIC_RE = re.compile(
    r"\.(?:css|js|mjs|png|jpe?g|webp|gif|svg|ico|avif|woff2?|ttf|otf|eot|json|xml|map|pdf)(?:[?#].*)?$",
    re.I,
)

def route_slug(route):
    if not route:
        return "home"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", route.strip("/")) or "home"

async def inspect_one(browser, base, route, label):
    url = urljoin(base, route)
    context = await browser.new_context(
        viewport={"width": 1440, "height": 1000},
        ignore_https_errors=True,
        locale="en-US",
        color_scheme="light",
    )
    page = await context.new_page()

    requests = []
    responses = []
    failed = []
    console_errors = []
    page_errors = []

    page.on("request", lambda req: requests.append({
        "url": req.url,
        "resource_type": req.resource_type,
        "method": req.method,
    }))
    page.on("response", lambda resp: responses.append({
        "url": resp.url,
        "status": resp.status,
        "resource_type": resp.request.resource_type,
        "content_type": resp.headers.get("content-type", ""),
    }))
    page.on("requestfailed", lambda req: failed.append({
        "url": req.url,
        "resource_type": req.resource_type,
        "failure": req.failure,
    }))
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    nav = None
    nav_error = None
    try:
        nav = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        nav_error = f"{type(exc).__name__}: {exc}"

    try:
        await page.wait_for_load_state("networkidle", timeout=12000)
    except Exception:
        pass

    try:
        await page.evaluate("""async () => {
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          for (let i = 0; i < 18; i++) {
            window.scrollBy(0, Math.max(500, innerHeight * 0.8));
            await sleep(100);
          }
          window.scrollTo(0, 0);
          await sleep(500);
        }""")
    except Exception:
        pass

    await page.wait_for_timeout(1500)

    slug = route_slug(route)
    screenshot = OUT / f"{slug}__{label}.jpg"
    try:
        await page.screenshot(path=str(screenshot), type="jpeg", quality=72, full_page=False)
    except Exception:
        pass

    dom = await page.evaluate("""(args) => {
      const { selectors, styleKeys } = args;

      const styleFor = (el) => {
        const s = getComputedStyle(el);
        const out = {};
        for (const k of styleKeys) out[k] = s[k];
        const r = el.getBoundingClientRect();
        out.__rect = {x:r.x,y:r.y,width:r.width,height:r.height};
        return out;
      };

      const styles = {};
      for (const sel of selectors) {
        const el = document.querySelector(sel);
        styles[sel] = el ? styleFor(el) : null;
      }

      const stylesheets = [...document.querySelectorAll('link[rel~="stylesheet"]')].map(el => ({
        href: el.href,
        media: el.media || "",
        disabled: !!el.disabled,
      }));

      const scripts = [...document.scripts].map(el => ({
        src: el.src || null,
        type: el.type || null,
        async: !!el.async,
        defer: !!el.defer,
      }));

      const images = [...document.images].map(el => ({
        src: el.currentSrc || el.src || "",
        declared_src: el.getAttribute('src'),
        complete: el.complete,
        naturalWidth: el.naturalWidth,
        naturalHeight: el.naturalHeight,
        width: el.getBoundingClientRect().width,
        height: el.getBoundingClientRect().height,
        alt: el.alt || "",
      }));

      const iframes = [...document.querySelectorAll('iframe')].map(el => ({
        src: el.src || el.getAttribute('src') || "",
        title: el.title || "",
        width: el.getBoundingClientRect().width,
        height: el.getBoundingClientRect().height,
      }));

      const links = [...document.querySelectorAll('link[rel]')].map(el => ({
        rel: el.rel,
        href: el.href,
        type: el.type || "",
      }));

      const performanceResources = performance.getEntriesByType('resource').map(e => ({
        name: e.name,
        initiatorType: e.initiatorType,
        transferSize: e.transferSize || 0,
        encodedBodySize: e.encodedBodySize || 0,
        decodedBodySize: e.decodedBodySize || 0,
        duration: e.duration || 0,
      }));

      const fonts = document.fonts ? [...document.fonts].map(f => ({
        family: f.family,
        style: f.style,
        weight: f.weight,
        status: f.status,
      })) : [];

      const brokenImages = images.filter(x => x.complete && x.naturalWidth === 0);

      return {
        title: document.title,
        url: location.href,
        htmlLang: document.documentElement.lang,
        bodyClass: document.body.className,
        bodyScrollHeight: document.body.scrollHeight,
        docScrollHeight: document.documentElement.scrollHeight,
        elementCount: document.querySelectorAll('*').length,
        styles,
        stylesheets,
        scripts,
        images,
        brokenImages,
        iframes,
        links,
        performanceResources,
        fonts,
      };
    }""", {"selectors": KEY_SELECTORS, "styleKeys": STYLE_KEYS})

    status = nav.status if nav else None

    # Cookie behavior on home only.
    cookie = None
    if route == "":
        cookie = {
            "visible_before": False,
            "clicked": False,
            "closed_after": False,
            "selector": None,
        }
        banner = page.locator(".termsfeed-com---nb")
        if await banner.count():
            try:
                cookie["visible_before"] = await banner.first.is_visible()
            except Exception:
                pass
        for sel in [".cc-nb-reject",".cc-nb-okagree",'button:has-text("Reject")','button:has-text("Accept")','button:has-text("Agree")']:
            loc = page.locator(sel)
            if await loc.count():
                try:
                    if await loc.first.is_visible():
                        cookie["selector"] = sel
                        await loc.first.click(timeout=4000)
                        cookie["clicked"] = True
                        break
                except Exception:
                    pass
        if cookie["clicked"]:
            await page.wait_for_timeout(800)
            try:
                cookie["closed_after"] = not await banner.first.is_visible() if await banner.count() else True
            except Exception:
                cookie["closed_after"] = True

    await context.close()

    return {
        "label": label,
        "requested_url": url,
        "status": status,
        "navigation_error": nav_error,
        "dom": dom,
        "requests": requests,
        "responses": responses,
        "failed_requests": failed,
        "bad_responses": [r for r in responses if r["status"] >= 400],
        "console_errors": console_errors,
        "page_errors": page_errors,
        "cookie": cookie,
        "screenshot": str(screenshot),
    }

def normalize_host_for_compare(url, base):
    try:
        p = urlparse(url)
        b = urlparse(base)
        if p.hostname == b.hostname:
            path = p.path
            if b.hostname == "openrocketsmaple.github.io" and path.startswith("/openrockets.com/"):
                path = path[len("/openrockets.com"):]
            return "SELF:" + path
        return p.hostname + p.path
    except Exception:
        return url

def compare_route(live, recovered):
    diffs = {
        "status": [live["status"], recovered["status"]],
        "styles": {},
        "missing_stylesheets": [],
        "extra_stylesheets": [],
        "broken_images_live": live["dom"]["brokenImages"],
        "broken_images_recovered": recovered["dom"]["brokenImages"],
        "failed_live": live["failed_requests"],
        "failed_recovered": recovered["failed_requests"],
        "bad_live": live["bad_responses"],
        "bad_recovered": recovered["bad_responses"],
        "console_live": live["console_errors"],
        "console_recovered": recovered["console_errors"],
        "page_errors_live": live["page_errors"],
        "page_errors_recovered": recovered["page_errors"],
    }

    for sel in KEY_SELECTORS:
        a = live["dom"]["styles"].get(sel)
        b = recovered["dom"]["styles"].get(sel)
        if a is None or b is None:
            if a != b:
                diffs["styles"][sel] = {"live": a, "recovered": b}
            continue
        delta = {}
        for k in STYLE_KEYS + ["__rect"]:
            if a.get(k) != b.get(k):
                delta[k] = {"live": a.get(k), "recovered": b.get(k)}
        if delta:
            diffs["styles"][sel] = delta

    live_css = {
        normalize_host_for_compare(x["href"], LIVE)
        for x in live["dom"]["stylesheets"]
    }
    rec_css = {
        normalize_host_for_compare(x["href"], RECOVERED)
        for x in recovered["dom"]["stylesheets"]
    }
    diffs["missing_stylesheets"] = sorted(live_css - rec_css)
    diffs["extra_stylesheets"] = sorted(rec_css - live_css)

    return diffs

async def main():
    report = {
        "generated_at_unix": int(time.time()),
        "live": LIVE,
        "recovered": RECOVERED,
        "routes": {},
    }

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"],
        )

        for route in ROUTES:
            print(f"Comparing route: /{route}", flush=True)
            live = await inspect_one(browser, LIVE, route, "live")
            recovered = await inspect_one(browser, RECOVERED, route, "recovered")
            report["routes"][route or "/"] = {
                "live": live,
                "recovered": recovered,
                "diff": compare_route(live, recovered),
            }

        await browser.close()

    (OUT / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = {}
    for route, item in report["routes"].items():
        summary[route] = {
            "live_status": item["live"]["status"],
            "recovered_status": item["recovered"]["status"],
            "style_selector_diff_count": len(item["diff"]["styles"]),
            "missing_stylesheet_count": len(item["diff"]["missing_stylesheets"]),
            "recovered_broken_image_count": len(item["diff"]["broken_images_recovered"]),
            "recovered_failed_request_count": len(item["diff"]["failed_recovered"]),
            "recovered_bad_response_count": len(item["diff"]["bad_recovered"]),
            "recovered_console_error_count": len(item["diff"]["console_recovered"]),
            "recovered_page_error_count": len(item["diff"]["page_errors_recovered"]),
        }

    print(json.dumps(summary, indent=2), flush=True)

asyncio.run(main())
