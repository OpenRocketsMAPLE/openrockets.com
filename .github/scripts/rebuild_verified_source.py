#!/usr/bin/env python3
import html
import json
import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urlunsplit, unquote

ROOT = Path(__file__).resolve().parents[2]
RECOVERY_COMMIT = "62419e53b1c7597f4f880d90aafc90e76b81336b"
HOST = "openrockets.com"

RAW_SOURCES = {
    "our-communities/index.html": "recovery_snapshot/assets/openrockets.com/6893f00551c19094e40a__our-communities.html",
    "team/index.html": "recovery_snapshot/assets/openrockets.com/3db835de620ddd30663b__team.html",
    "merch/index.html": "recovery_snapshot/assets/openrockets.com/fb1368330b36a493b870__merch.html",
    "join.html": "recovery_snapshot/assets/openrockets.com/3ecb624db10d9483bf4a__join.html",
    "research/maple/v1/index.html": "recovery_snapshot/assets/openrockets.com/cd17e7950ec2288b3a6d__v1.html",
    "magazinesoftware/signup/index.html": "recovery_snapshot/assets/openrockets.com/098ed40f749d5b69f8cd__signup.html",
    "merch/cart.html": "recovery_snapshot/assets/openrockets.com/a8e9b9b49e8c713336e5__cart.html",
    "merch/product.html": "recovery_snapshot/assets/openrockets.com/db075b40c1dc66bf7bbf__product.html",
    "team/management-profile.html": "recovery_snapshot/assets/openrockets.com/d5bcd9acec1d00d749aa__management-profile.html",
}

STATIC_EXTS = {
    ".css",".js",".mjs",".cjs",".json",".xml",".txt",".map",
    ".png",".jpg",".jpeg",".webp",".gif",".svg",".ico",".avif",
    ".woff",".woff2",".ttf",".otf",".eot",".pdf",".mp3",".wav",".ogg",".mp4",".webm"
}

def git_show(path: str) -> bytes:
    return subprocess.check_output(["git","show",f"{RECOVERY_COMMIT}:{path}"])

def decode_cf(hexstr: str):
    try:
        b=bytes.fromhex(hexstr)
        if len(b)<2:
            return None
        key=b[0]
        return bytes(x ^ key for x in b[1:]).decode("utf-8")
    except Exception:
        return None

def strip_cloudflare_edge(text: str) -> str:
    # Decode Cloudflare email-protection anchors/spans into ordinary public mailto links.
    def href_repl(m):
        email=decode_cf(m.group(1))
        return f'href="mailto:{html.escape(email, quote=True)}"' if email else m.group(0)
    text=re.sub(
        r'href=["\']/cdn-cgi/l/email-protection#([0-9a-fA-F]+)["\']',
        href_repl, text, flags=re.I
    )

    def span_repl(m):
        email=decode_cf(m.group(1))
        return html.escape(email) if email else m.group(0)
    text=re.sub(
        r'<span\b[^>]*class=["\'][^"\']*__cf_email__[^"\']*["\'][^>]*data-cfemail=["\']([0-9a-fA-F]+)["\'][^>]*>[\s\S]*?</span>',
        span_repl, text, flags=re.I
    )

    # Email decoder is no longer needed after decoding.
    text=re.sub(
        r'<script\b[^>]*src=["\'][^"\']*cdn-cgi/scripts/[^"\']*email-decode\.min\.js["\'][^>]*>\s*</script>',
        "", text, flags=re.I
    )

    # Remove Cloudflare challenge injection and analytics beacon: these belong to
    # the original hosting edge, not the recovered site.
    text=re.sub(
        r'<script\b[^>]*>[\s\S]*?__CF\$cv\$params[\s\S]*?</script>',
        "", text, flags=re.I
    )
    text=re.sub(
        r'<script\b[^>]*src=["\']https://static\.cloudflareinsights\.com/beacon\.min\.js[^"\']*["\'][^>]*>\s*</script>',
        "", text, flags=re.I
    )
    return text

def safe_rel_target(path: str):
    path=unquote(path or "").replace("\\","/")
    rel=path.lstrip("/")
    if not rel:
        return None
    parts=PurePosixPath(rel).parts
    if any(x in ("",".","..") for x in parts):
        return None
    return Path(*parts)

def route_relative(file_path: Path, raw: str):
    raw=html.unescape(raw.strip()).replace("\\","/")
    if not raw or raw.startswith(("#","data:","blob:","javascript:","mailto:","tel:")):
        return raw

    p=urlsplit(raw)
    same_host=False
    if p.scheme in ("http","https"):
        if (p.hostname or "").lower()!=HOST:
            return raw
        same_host=True
    elif p.scheme or raw.startswith("//"):
        return raw

    if p.scheme in ("http","https"):
        site_path=p.path or "/"
    elif raw.startswith("/"):
        site_path=p.path
    else:
        return raw

    target=site_path.lstrip("/")
    if not target:
        target="index.html"

    start=file_path.parent.relative_to(ROOT).as_posix()
    if start==".":
        start="."
    rel=posixpath.relpath(target,start=start)
    if site_path.endswith("/") and not rel.endswith("/"):
        rel += "/"
    if site_path=="/" and rel=="index.html":
        rel="./"
    return urlunsplit(("", "", rel, p.query, p.fragment))

ATTR_RE=re.compile(
    r'(?P<prefix>\b(?:href|src|poster|action|data-src|data-lazy-src|data-original)\s*=\s*(?P<q>["\']))'
    r'(?P<url>[^"\']*)'
    r'(?P<suffix>(?P=q))', re.I
)
SRCSET_RE=re.compile(
    r'(?P<prefix>\b(?:srcset|data-srcset)\s*=\s*(?P<q>["\']))'
    r'(?P<value>[^"\']*)'
    r'(?P<suffix>(?P=q))', re.I
)
CSS_URL_RE=re.compile(r'url\(\s*(?P<q>["\']?)(?P<url>[^)"\']+)(?P=q)\s*\)',re.I)

def normalize_html(file_path: Path, text: str):
    text=strip_cloudflare_edge(text)

    def attr_sub(m):
        raw=m.group("url").strip().replace("\\","/")
        new=route_relative(file_path,raw)
        return m.group("prefix")+new+m.group("suffix")
    text=ATTR_RE.sub(attr_sub,text)

    def srcset_sub(m):
        out=[]
        for item in m.group("value").split(","):
            item=item.strip()
            if not item:
                continue
            bits=item.split()
            url=route_relative(file_path,bits[0].replace("\\","/"))
            out.append(" ".join([url]+bits[1:]))
        return m.group("prefix")+", ".join(out)+m.group("suffix")
    text=SRCSET_RE.sub(srcset_sub,text)

    def css_sub(m):
        raw=m.group("url").strip().replace("\\","/")
        new=route_relative(file_path,raw)
        q=m.group("q")
        return f"url({q}{new}{q})"
    text=CSS_URL_RE.sub(css_sub,text)

    return text

def insert_base(text: str, href="../"):
    if re.search(r'<base\b',text,re.I):
        return text
    return re.sub(r'(<head(?:\s[^>]*)?>)',r'\1\n<base href="'+href+r'">',text,count=1,flags=re.I)

# Restore clean HTTP source for pages that had browser-rendered snapshots.
for target, historical in RAW_SOURCES.items():
    path=ROOT/target
    raw=git_show(historical).decode("utf-8",errors="ignore")
    cleaned=normalize_html(path,raw)
    if target=="magazinesoftware/signup/index.html":
        cleaned=insert_base(cleaned,"../")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(cleaned,encoding="utf-8")

# Normalize the already-clean homepage too, preserving recent content while
# removing edge-only artifacts and malformed path separators.
home=ROOT/"index.html"
home.write_text(normalize_html(home,home.read_text(encoding="utf-8",errors="ignore")),encoding="utf-8")

# Canonical extensionless aliases. <base> preserves the resolution behavior of
# the original extensionless URL without rewriting every relative asset.
aliases={
    "join/index.html":"join.html",
    "merch/cart/index.html":"merch/cart.html",
    "merch/product/index.html":"merch/product.html",
    "team/management-profile/index.html":"team/management-profile.html",
}
for dst,src in aliases.items():
    source=(ROOT/src).read_text(encoding="utf-8",errors="ignore")
    path=ROOT/dst
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(insert_base(source,"../"),encoding="utf-8")

# Preserve the two known external redirects.
def redirect_doc(target,title):
    q=json.dumps(target)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url={html.escape(target,quote=True)}">
<link rel="canonical" href="{html.escape(target,quote=True)}">
<title>{html.escape(title)}</title>
<script>location.replace({q}+location.search+location.hash);</script>
</head><body><p>Redirecting to <a href="{html.escape(target,quote=True)}">{html.escape(target)}</a>…</p></body></html>'''
(ROOT/"opensource").mkdir(exist_ok=True)
(ROOT/"opensource/index.html").write_text(redirect_doc("https://maplelicense.substack.com/","Maple License"),encoding="utf-8")
(ROOT/"interkid").mkdir(exist_ok=True)
(ROOT/"interkid/index.html").write_text(redirect_doc("https://www.interkid.org/","InterKid"),encoding="utf-8")

# Remove redundant rendered query snapshots. Query parameters are handled by
# the clean generic product/profile shells.
for pattern in [
    "team/management-profile__query_*.html",
    "merch/product__query_*.html",
]:
    for p in ROOT.glob(pattern):
        p.unlink()

# Normalize root-relative URLs in local CSS only. External CSS stays external.
for css in ROOT.rglob("*.css"):
    relparts=css.relative_to(ROOT).parts
    if relparts and relparts[0] in (".git",".github","vendor","_vendor"):
        continue
    text=css.read_text(encoding="utf-8",errors="ignore")
    def repl(m):
        raw=m.group("url").strip().replace("\\","/")
        if raw.startswith("/") and not raw.startswith("//"):
            p=urlsplit(raw)
            target=p.path.lstrip("/")
            start=css.parent.relative_to(ROOT).as_posix()
            if start==".":
                start="."
            r=posixpath.relpath(target,start=start)
            r=urlunsplit(("", "", r, p.query, p.fragment))
            q=m.group("q")
            return f"url({q}{r}{q})"
        return m.group(0)
    css.write_text(CSS_URL_RE.sub(repl,text),encoding="utf-8")

# Load verified crawl URL -> saved-file map so any genuinely missing same-host
# static asset can be restored from the verified archive without refetching.
mapping=json.loads(git_show("recovery_snapshot/metadata/url_to_saved_file.json").decode("utf-8"))
map_by_path={}
for url,saved in mapping.items():
    try:
        p=urlsplit(url)
    except Exception:
        continue
    if (p.hostname or "").lower()!=HOST:
        continue
    key=unquote(p.path or "").lstrip("/")
    if key:
        map_by_path.setdefault(key,saved)

static_ref_re=re.compile(
    r'\.(?:css|js|mjs|cjs|json|xml|txt|map|png|jpe?g|webp|gif|svg|ico|avif|woff2?|ttf|otf|eot|pdf|mp3|wav|ogg|mp4|webm)(?:[?#].*)?$',
    re.I
)

def local_refs(html_file: Path):
    text=html_file.read_text(encoding="utf-8",errors="ignore")
    vals=[m.group("url") for m in ATTR_RE.finditer(text)]
    for m in SRCSET_RE.finditer(text):
        vals += [x.strip().split()[0] for x in m.group("value").split(",") if x.strip()]
    vals += [m.group("url") for m in CSS_URL_RE.finditer(text)]
    for raw in vals:
        raw=html.unescape(raw.strip()).replace("\\","/")
        if not raw or raw.startswith(("#","data:","blob:","javascript:","mailto:","tel:","//","http://","https://")):
            continue
        clean=urlsplit(raw).path
        if not static_ref_re.search(clean):
            continue
        candidate=(html_file.parent/clean).resolve()
        try:
            rel=candidate.relative_to(ROOT.resolve())
        except Exception:
            continue
        yield rel

missing_before=[]
restored=[]
html_files=[
    p for p in ROOT.rglob("*.html")
    if not any(x in p.parts for x in (".git",".github","vendor","_vendor"))
]
for hp in html_files:
    for rel in local_refs(hp):
        target=ROOT/rel
        if target.exists():
            continue
        key=rel.as_posix()
        missing_before.append({"html":hp.relative_to(ROOT).as_posix(),"target":key})
        saved=map_by_path.get(key)
        if saved:
            try:
                body=git_show("recovery_snapshot/"+saved)
                # Never restore a soft-404 HTML body under a static extension.
                head=body[:4096].lstrip().lower()
                if not (head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<html" in head[:1000]):
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(body)
                    restored.append(key)
            except Exception:
                pass

# Final static-reference integrity check.
missing_after=[]
for hp in html_files:
    for rel in local_refs(hp):
        if not (ROOT/rel).exists():
            missing_after.append({"html":hp.relative_to(ROOT).as_posix(),"target":rel.as_posix()})

# Basic sanity gates.
index=(ROOT/"index.html").read_text(encoding="utf-8",errors="ignore")
assert "www.termsfeed.com/public/cookie-consent" in index, "TermsFeed source missing"
assert "cookieconsent.run(" in index, "TermsFeed initialization missing"
assert "cloudflareinsights.com/beacon.min.js" not in index, "Cloudflare beacon still injected"
assert "/cdn-cgi/challenge-platform/" not in index, "Cloudflare challenge still injected"

report={
    "raw_pages_restored":sorted(RAW_SOURCES),
    "query_snapshots_removed":True,
    "missing_before":missing_before,
    "restored_from_verified_archive":sorted(set(restored)),
    "missing_after":missing_after,
}
report_path=ROOT/".github/recovery-audit/source-rebuild.json"
report_path.parent.mkdir(parents=True,exist_ok=True)
report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({
    "raw_pages_restored":len(RAW_SOURCES),
    "missing_before":len(missing_before),
    "restored":len(set(restored)),
    "missing_after":len(missing_after),
},indent=2))

if missing_after:
    raise SystemExit(f"FAIL: {len(missing_after)} referenced local static asset(s) are still missing")
