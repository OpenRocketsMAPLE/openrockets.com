#!/usr/bin/env python3
import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

SITE = "https://openrocketsmaple.github.io/openrockets.com/"
PROJECT_PREFIX = "/openrockets.com/"
REPORT = Path(".github/recovery-audit/pages-smoke.json")

ROUTES = [
    "",
    "our-communities/",
    "team/",
    "merch/",
    "join.html",
]

STATIC_RE = re.compile(
    r"\.(?:css|js|mjs|png|jpe?g|webp|gif|svg|ico|avif|woff2?|ttf|otf|eot|json|xml|map|pdf)(?:[?#].*)?$",
    re.I,
)

async def main():
    failed_requests = []
    bad_responses = []
    console_errors = []
    route_results = []
    same_site_assets = set()
    escaped_project_urls = set()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        page.on(
            "requestfailed",
            lambda req: failed_requests.append({
                "url": req.url,
                "resource_type": req.resource_type,
                "failure": req.failure,
            }),
        )

        def on_response(resp):
            if resp.status >= 400:
                bad_responses.append({
                    "url": resp.url,
                    "status": resp.status,
                    "resource_type": resp.request.resource_type,
                })

        page.on("response", on_response)
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type == "error"
            else None,
        )

        homepage_cookie = {
            "banner_count_before": 0,
            "banner_visible_before": False,
            "action_selector": None,
            "clicked": False,
            "closed_after_click": False,
        }

        favicon_href = None
        favicon_url = None
        favicon_status = None

        site_host = urlparse(SITE).hostname

        for index, route in enumerate(ROUTES):
            url = urljoin(SITE, route)
            before_bad = len(bad_responses)
            before_failed = len(failed_requests)
            before_console = len(console_errors)

            resp = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            status = resp.status if resp else None

            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            await page.wait_for_timeout(1800)
            title = await page.title()

            if index == 0:
                icon = page.locator('link[rel~="icon"]')
                if await icon.count():
                    favicon_href = await icon.first.get_attribute("href")
                    if favicon_href:
                        favicon_url = urljoin(SITE, favicon_href)
                        fr = await context.request.get(
                            favicon_url,
                            fail_on_status_code=False,
                            timeout=20000,
                        )
                        favicon_status = fr.status

                banner_selector = ".termsfeed-com---nb"
                banner = page.locator(banner_selector)
                homepage_cookie["banner_count_before"] = await banner.count()

                if homepage_cookie["banner_count_before"]:
                    try:
                        homepage_cookie["banner_visible_before"] = await banner.first.is_visible()
                    except Exception:
                        pass

                candidates = [
                    ".cc-nb-reject",
                    ".cc-nb-okagree",
                    'button:has-text("Reject")',
                    'button:has-text("Accept")',
                    'button:has-text("Agree")',
                ]

                for selector in candidates:
                    loc = page.locator(selector)
                    if await loc.count():
                        try:
                            if await loc.first.is_visible():
                                homepage_cookie["action_selector"] = selector
                                await loc.first.click(timeout=5000)
                                homepage_cookie["clicked"] = True
                                break
                        except Exception:
                            pass

                if homepage_cookie["clicked"]:
                    await page.wait_for_timeout(1200)
                    try:
                        if await banner.count():
                            homepage_cookie["closed_after_click"] = not await banner.first.is_visible()
                        else:
                            homepage_cookie["closed_after_click"] = True
                    except Exception:
                        homepage_cookie["closed_after_click"] = True

            urls = await page.evaluate("""() => {
              const out = [];
              for (const el of document.querySelectorAll('*')) {
                for (const attr of ['src', 'href', 'poster']) {
                  if (el.hasAttribute && el.hasAttribute(attr)) {
                    out.push(el.getAttribute(attr));
                  }
                }
                const ss = el.getAttribute && el.getAttribute('srcset');
                if (ss) {
                  out.push(...ss.split(',').map(x => x.trim().split(/\s+/)[0]));
                }
              }
              return out.filter(Boolean);
            }""")

            resolved_route_assets = set()
            for raw in urls:
                try:
                    resolved = urljoin(url, raw)
                    parsed = urlparse(resolved)
                except Exception:
                    continue

                if parsed.hostname != site_host:
                    continue

                if STATIC_RE.search(parsed.path):
                    same_site_assets.add(resolved)
                    resolved_route_assets.add(resolved)

                    if not parsed.path.startswith(PROJECT_PREFIX):
                        escaped_project_urls.add(resolved)

            route_results.append({
                "route": route or "/",
                "url": url,
                "status": status,
                "title": title,
                "same_site_static_assets_seen": len(resolved_route_assets),
                "bad_responses_during_route": bad_responses[before_bad:],
                "failed_requests_during_route": failed_requests[before_failed:],
                "console_errors_during_route": console_errors[before_console:],
            })

        probe_results = []
        semaphore = asyncio.Semaphore(20)

        async def probe(url):
            async with semaphore:
                try:
                    response = await context.request.get(
                        url,
                        fail_on_status_code=False,
                        timeout=15000,
                    )
                    return {"url": url, "status": response.status}
                except Exception as exc:
                    return {
                        "url": url,
                        "status": None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }

        if same_site_assets:
            probe_results = await asyncio.gather(
                *(probe(url) for url in sorted(same_site_assets))
            )

        broken_same_site = [
            item
            for item in probe_results
            if item.get("status") is None or item.get("status", 0) >= 400
        ]

        report = {
            "generated_at_unix": int(time.time()),
            "site": SITE,
            "routes": route_results,
            "favicon_href": favicon_href,
            "favicon_url": favicon_url,
            "favicon_status": favicon_status,
            "cookie_banner_count_before": homepage_cookie["banner_count_before"],
            "cookie_banner_visible_before": homepage_cookie["banner_visible_before"],
            "cookie_action_selector": homepage_cookie["action_selector"],
            "cookie_clicked": homepage_cookie["clicked"],
            "cookie_closed_after_click": homepage_cookie["closed_after_click"],
            "same_site_assets_probed": len(probe_results),
            "escaped_project_static_urls": sorted(escaped_project_urls),
            "broken_same_site_assets": broken_same_site,
            "browser_bad_responses": bad_responses[:800],
            "browser_failed_requests": failed_requests[:800],
            "console_errors": console_errors[:300],
        }

        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        summary = {
            "route_statuses": {
                item["route"]: item["status"]
                for item in route_results
            },
            "favicon_status": favicon_status,
            "cookie_banner_visible_before": homepage_cookie["banner_visible_before"],
            "cookie_clicked": homepage_cookie["clicked"],
            "cookie_closed_after_click": homepage_cookie["closed_after_click"],
            "same_site_assets_probed": len(probe_results),
            "escaped_project_static_url_count": len(escaped_project_urls),
            "broken_same_site_asset_count": len(broken_same_site),
            "bad_response_count": len(bad_responses),
            "failed_request_count": len(failed_requests),
            "console_error_count": len(console_errors),
        }
        print(json.dumps(summary, indent=2))

        await context.close()
        await browser.close()

        bad_routes = [
            item for item in route_results
            if item["status"] != 200
        ]
        if bad_routes:
            raise SystemExit(
                "FAIL route status: "
                + ", ".join(f'{x["route"]}={x["status"]}' for x in bad_routes)
            )

        if favicon_url and favicon_status != 200:
            raise SystemExit(
                f"FAIL favicon status {favicon_status}: {favicon_url}"
            )

        if (
            homepage_cookie["banner_visible_before"]
            and not homepage_cookie["closed_after_click"]
        ):
            raise SystemExit("FAIL cookie banner did not close after click")

        if escaped_project_urls:
            raise SystemExit(
                f"FAIL {len(escaped_project_urls)} static URL(s) escaped project prefix"
            )

        if broken_same_site:
            raise SystemExit(
                f"FAIL {len(broken_same_site)} same-site static asset(s) are broken"
            )

asyncio.run(main())
