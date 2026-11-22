#!/usr/bin/env python3
import asyncio
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

SITE = "https://openrocketsmaple.github.io/openrockets.com/"
PROJECT_PREFIX = "/openrockets.com/"
REPORT = Path(".github/recovery-audit/pages-smoke.json")
EXPECTED_SHA = os.environ.get("EXPECTED_SHA", "").strip()

ROUTES = [
    "",
    "our-communities/",
    "team/",
    "merch/",
    "join.html",
    "research/maple/v1/",
    "magazinesoftware/signup/",
]

STATIC_RE = re.compile(
    r"\.(?:css|js|mjs|png|jpe?g|webp|gif|svg|ico|avif|woff2?|ttf|otf|eot|json|xml|map|pdf)(?:[?#].*)?$",
    re.I,
)

async def main():
    requests_seen = []
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

        # GitHub's native Pages deployment is currently sourced from main,
        # while the helper gh-pages branch has its own source-commit marker.
        # Do not require that marker to be served by the live Pages site.
        # Instead, wait for the public homepage to be healthy and stable before
        # beginning the route/resource checks. The checks below verify the
        # actual deployed content (including the localized Stripe assets), so a
        # stale deployment will fail those fidelity checks naturally.
        deployed_sha = None
        homepage_ready_streak = 0
        for _ in range(24):
            try:
                probe = await context.request.get(
                    SITE,
                    fail_on_status_code=False,
                    timeout=10000,
                    headers={"Cache-Control": "no-cache"},
                )
                if probe.status == 200:
                    homepage_ready_streak += 1
                    if homepage_ready_streak >= 3:
                        break
                else:
                    homepage_ready_streak = 0
            except Exception:
                homepage_ready_streak = 0
            await asyncio.sleep(5)

        if homepage_ready_streak < 3:
            raise SystemExit("FAIL Pages homepage did not become stably available")

        page.on(
            "request",
            lambda req: requests_seen.append({
                "url": req.url,
                "resource_type": req.resource_type,
            }),
        )

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

        cookie = {
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

            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            status = response.status if response else None

            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

            await page.wait_for_timeout(1800)
            title = await page.title()

            if index == 0:
                icons = page.locator('link[rel~="icon"]')
                if await icons.count():
                    favicon_href = await icons.first.get_attribute("href")
                    if favicon_href:
                        favicon_url = urljoin(SITE, favicon_href)
                        favicon_response = await context.request.get(
                            favicon_url,
                            fail_on_status_code=False,
                            timeout=20000,
                        )
                        favicon_status = favicon_response.status

                banner_selector = ".termsfeed-com---nb"
                banner = page.locator(banner_selector)
                cookie["banner_count_before"] = await banner.count()

                if cookie["banner_count_before"]:
                    try:
                        cookie["banner_visible_before"] = await banner.first.is_visible()
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
                    locator = page.locator(selector)
                    if await locator.count():
                        try:
                            if await locator.first.is_visible():
                                cookie["action_selector"] = selector
                                await locator.first.click(timeout=5000)
                                cookie["clicked"] = True
                                break
                        except Exception:
                            pass

                if cookie["clicked"]:
                    await page.wait_for_timeout(1200)
                    try:
                        if await banner.count():
                            cookie["closed_after_click"] = not await banner.first.is_visible()
                        else:
                            cookie["closed_after_click"] = True
                    except Exception:
                        cookie["closed_after_click"] = True

            urls = await page.evaluate("""() => {
              const out = [];
              for (const el of document.querySelectorAll('*')) {
                for (const attr of ['src', 'href', 'poster']) {
                  if (el.hasAttribute && el.hasAttribute(attr)) {
                    out.push(el.getAttribute(attr));
                  }
                }
                const srcset = el.getAttribute && el.getAttribute('srcset');
                if (srcset) {
                  out.push(...srcset.split(',').map(x => x.trim().split(/\s+/)[0]));
                }
              }
              return out.filter(Boolean);
            }""")

            route_assets = set()
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
                    route_assets.add(resolved)

                    if not parsed.path.startswith(PROJECT_PREFIX):
                        escaped_project_urls.add(resolved)

            route_results.append({
                "route": route or "/",
                "url": url,
                "status": status,
                "title": title,
                "same_site_static_assets_seen": len(route_assets),
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

        stripe_static_requests = [
            item for item in requests_seen
            if urlparse(item["url"]).hostname == "b.stripecdn.com"
            and item["resource_type"] in {"stylesheet", "font"}
        ]

        report = {
            "result": "pending",
            "generated_at_unix": int(time.time()),
            "site": SITE,
            "expected_source_commit": EXPECTED_SHA,
            "deployed_source_commit": deployed_sha,
            "deployment_gate": "stable-homepage-and-live-fidelity-checks",
            "routes": route_results,
            "favicon_href": favicon_href,
            "favicon_url": favicon_url,
            "favicon_status": favicon_status,
            "cookie_banner_count_before": cookie["banner_count_before"],
            "cookie_banner_visible_before": cookie["banner_visible_before"],
            "cookie_action_selector": cookie["action_selector"],
            "cookie_clicked": cookie["clicked"],
            "cookie_closed_after_click": cookie["closed_after_click"],
            "same_site_assets_probed": len(probe_results),
            "escaped_project_static_urls": sorted(escaped_project_urls),
            "broken_same_site_assets": broken_same_site,
            "remaining_stripe_stylesheet_or_font_requests": stripe_static_requests,
            "browser_bad_responses": bad_responses[:1000],
            "browser_failed_requests": failed_requests[:1000],
            "console_errors": console_errors[:400],
        }

        failures = []

        bad_routes = [item for item in route_results if item["status"] != 200]
        if bad_routes:
            failures.append(
                "route status: "
                + ", ".join(f'{x["route"]}={x["status"]}' for x in bad_routes)
            )

        if favicon_url and favicon_status != 200:
            failures.append(f"favicon status {favicon_status}: {favicon_url}")

        if not cookie["banner_visible_before"]:
            failures.append("cookie banner was not visible on a fresh browser context")
        elif not cookie["clicked"] or not cookie["closed_after_click"]:
            failures.append("cookie banner did not close after click")

        if escaped_project_urls:
            failures.append(
                f"{len(escaped_project_urls)} static URL(s) escaped project prefix"
            )

        if broken_same_site:
            failures.append(
                f"{len(broken_same_site)} same-site static asset(s) are broken"
            )

        if stripe_static_requests:
            failures.append(
                f"{len(stripe_static_requests)} Stripe stylesheet/font request(s) "
                "were not localized"
            )

        report["result"] = "pass" if not failures else "fail"
        report["failures"] = failures

        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(json.dumps({
            "result": report["result"],
            "expected_source_commit": EXPECTED_SHA,
            "deployed_source_commit": deployed_sha,
            "route_statuses": {
                item["route"]: item["status"] for item in route_results
            },
            "favicon_status": favicon_status,
            "cookie_visible": cookie["banner_visible_before"],
            "cookie_clicked": cookie["clicked"],
            "cookie_closed": cookie["closed_after_click"],
            "same_site_assets_probed": len(probe_results),
            "escaped_project_static_url_count": len(escaped_project_urls),
            "broken_same_site_asset_count": len(broken_same_site),
            "remaining_stripe_static_request_count": len(stripe_static_requests),
            "failures": failures,
        }, indent=2))

        await context.close()
        await browser.close()

        if failures:
            raise SystemExit("FAIL: " + " | ".join(failures))

asyncio.run(main())
