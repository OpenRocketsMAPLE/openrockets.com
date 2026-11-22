#!/usr/bin/env python3
import asyncio, json, re, time
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright

SITE="https://openrocketsmaple.github.io/openrockets.com/"
REPORT=".github/recovery-audit/pages-smoke.json"

async def main():
    failed_requests=[]
    bad_responses=[]
    same_site_assets=set()
    console_errors=[]

    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        context=await browser.new_context(
            viewport={"width":1440,"height":1000},
            ignore_https_errors=True,
        )
        page=await context.new_page()

        page.on("requestfailed", lambda req: failed_requests.append({
            "url":req.url,
            "resource_type":req.resource_type,
            "failure": req.failure
        }))

        def on_response(resp):
            if resp.status >= 400:
                bad_responses.append({
                    "url":resp.url,
                    "status":resp.status,
                    "resource_type":resp.request.resource_type
                })
        page.on("response", on_response)

        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type=="error" else None)

        resp=await page.goto(SITE,wait_until="domcontentloaded",timeout=45000)
        homepage_status=resp.status if resp else None
        try:
            await page.wait_for_load_state("networkidle",timeout=12000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)

        title=await page.title()

        # Favicon
        favicon_href=await page.locator('link[rel~="icon"]').first.get_attribute("href") if await page.locator('link[rel~="icon"]').count() else None
        favicon_url=urljoin(SITE,favicon_href) if favicon_href else None
        favicon_status=None
        if favicon_url:
            fr=await context.request.get(favicon_url,fail_on_status_code=False,timeout=20000)
            favicon_status=fr.status

        # Cookie banner behavior.
        banner_selector=".termsfeed-com---nb"
        banner_count_before=await page.locator(banner_selector).count()
        banner_visible_before=False
        if banner_count_before:
            try:
                banner_visible_before=await page.locator(banner_selector).first.is_visible()
            except Exception:
                pass

        cookie_action=None
        cookie_clicked=False
        cookie_closed=False

        # Prefer Reject so we do not opt into tracking during testing.
        candidate_selectors=[
            ".cc-nb-reject",
            ".cc-nb-okagree",
            'button:has-text("Reject")',
            'button:has-text("Accept")',
            'button:has-text("Agree")'
        ]
        for sel in candidate_selectors:
            loc=page.locator(sel)
            if await loc.count():
                try:
                    if await loc.first.is_visible():
                        cookie_action=sel
                        await loc.first.click(timeout=5000)
                        cookie_clicked=True
                        break
                except Exception:
                    pass

        if cookie_clicked:
            await page.wait_for_timeout(1200)
            try:
                cookie_closed = not await page.locator(banner_selector).first.is_visible() if await page.locator(banner_selector).count() else True
            except Exception:
                cookie_closed=True

        # Collect browser-resolved static URLs from DOM and explicitly probe same Pages-host assets.
        urls=await page.evaluate("""() => {
          const out=[];
          for (const el of document.querySelectorAll('*')) {
            for (const a of ['src','href','poster']) {
              if (el.hasAttribute && el.hasAttribute(a)) out.push(el.getAttribute(a));
            }
            const ss=el.getAttribute && el.getAttribute('srcset');
            if (ss) out.push(...ss.split(',').map(x=>x.trim().split(/\\s+/)[0]));
          }
          return out.filter(Boolean);
        }""")

        static_re=re.compile(r"\.(?:css|js|mjs|png|jpe?g|webp|gif|svg|ico|avif|woff2?|ttf|otf|eot|json|xml|map)(?:[?#].*)?$",re.I)
        page_host=urlparse(SITE).hostname

        for raw in urls:
            u=urljoin(SITE,raw)
            p=urlparse(u)
            if p.hostname==page_host and static_re.search(p.path):
                same_site_assets.add(u)

        probe_results=[]
        sem=asyncio.Semaphore(20)
        async def probe(u):
            async with sem:
                try:
                    r=await context.request.get(u,fail_on_status_code=False,timeout=15000)
                    return {"url":u,"status":r.status}
                except Exception as e:
                    return {"url":u,"status":None,"error":f"{type(e).__name__}: {e}"}

        if same_site_assets:
            probe_results=await asyncio.gather(*(probe(u) for u in sorted(same_site_assets)))

        broken_same_site=[x for x in probe_results if x.get("status") is None or x.get("status",0)>=400]

        report={
            "generated_at_unix":int(time.time()),
            "site":SITE,
            "homepage_status":homepage_status,
            "title":title,
            "favicon_href":favicon_href,
            "favicon_url":favicon_url,
            "favicon_status":favicon_status,
            "cookie_banner_count_before":banner_count_before,
            "cookie_banner_visible_before":banner_visible_before,
            "cookie_action_selector":cookie_action,
            "cookie_clicked":cookie_clicked,
            "cookie_closed_after_click":cookie_closed,
            "same_site_assets_probed":len(probe_results),
            "broken_same_site_assets":broken_same_site,
            "browser_bad_responses":bad_responses[:500],
            "browser_failed_requests":failed_requests[:500],
            "console_errors":console_errors[:200],
        }

        import pathlib
        path=pathlib.Path(REPORT)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")

        print(json.dumps({
            "homepage_status":homepage_status,
            "title":title,
            "favicon_status":favicon_status,
            "cookie_banner_visible_before":banner_visible_before,
            "cookie_clicked":cookie_clicked,
            "cookie_closed_after_click":cookie_closed,
            "same_site_assets_probed":len(probe_results),
            "broken_same_site_asset_count":len(broken_same_site),
            "bad_response_count":len(bad_responses),
            "failed_request_count":len(failed_requests),
            "console_error_count":len(console_errors),
        },indent=2))

        await context.close()
        await browser.close()

        if homepage_status != 200:
            raise SystemExit(f"FAIL homepage status {homepage_status}")
        if favicon_url and favicon_status != 200:
            raise SystemExit(f"FAIL favicon status {favicon_status}: {favicon_url}")
        if banner_visible_before and not cookie_closed:
            raise SystemExit("FAIL cookie banner did not close after click")
        if broken_same_site:
            raise SystemExit(f"FAIL {len(broken_same_site)} same-site static asset(s) are broken")

asyncio.run(main())

# rerun after route-aware path normalization
