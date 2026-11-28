import asyncio, json, pathlib
from playwright.async_api import async_playwright
OUT = pathlib.Path("header-evidence")
OUT.mkdir(exist_ok=True)
URLS = {
    "home": "https://openrockets.com/",
    "merch": "https://openrockets.com/merch/",
    "cart": "https://openrockets.com/merch/cart/",
    "product": "https://openrockets.com/merch/product/?id=1",
    "team": "https://openrockets.com/team/",
    "maple": "https://maple.openrockets.com/",
    "opensource": "https://opensource.openrockets.com/",
    "pages-home": "https://openrocketsmaple.github.io/openrockets.com/",
    "pages-merch": "https://openrocketsmaple.github.io/openrockets.com/merch/",
}
SNAPSHOT = """() => {
 const rect = e => {let r=e.getBoundingClientRect(); return [r.x,r.y,r.width,r.height].map(v=>Math.round(v*10)/10)};
 const props = ['display','color','backgroundColor','borderTopColor','borderTopWidth','borderRadius','fontFamily','fontSize','fontWeight','lineHeight','padding','gap','filter','height','width','visibility'];
 const style = e => Object.fromEntries(props.map(k=>[k,getComputedStyle(e)[k]]));
 let h=document.querySelector('#main-header:not(iframe),#master-header,.master-header,header.navigation,header.master-bar') || [...document.querySelectorAll('header')].find(e=>e.innerText.includes('Join / Start a Group'));
 if (!h) return null;
 let a=[...h.querySelectorAll('a,button')].filter(e=>e.innerText.trim()&&e.getBoundingClientRect().width);
 return {header:{rect:rect(h),style:style(h)},buttons:a.map(e=>({text:e.innerText.trim(),rect:rect(e),style:style(e),icon:e.querySelector('i,svg')?{tag:e.querySelector('i,svg').tagName,pseudo:getComputedStyle(e.querySelector('i,svg'),'::before').content,font:getComputedStyle(e.querySelector('i,svg'),'::before').fontFamily}:null})),logo:[...h.querySelectorAll('img')].map(e=>({src:e.currentSrc,loaded:e.complete&&e.naturalWidth>0,rect:rect(e)}))};
}"""
async def main():
 async with async_playwright() as pw:
  b=await pw.chromium.launch()
  for width in (1920,390):
   ctx=await b.new_context(viewport={"width":width,"height":900},device_scale_factor=1)
   async def inspect(name,url):
    p=await ctx.new_page()
    try:
     r=await p.goto(url,wait_until="domcontentloaded",timeout=25000)
     await p.wait_for_timeout(2500)
     found=[]
     for f in p.frames:
      try:
       result=await f.evaluate(SNAPSHOT)
       if result: found.append({"frame":f.url,**result})
      except Exception: pass
     print(json.dumps({"name":name,"width":width,"url":p.url,"status":r.status if r else None,"headers":found,"frame_urls":[f.url for f in p.frames]},ensure_ascii=False),flush=True)
     await p.screenshot(path=str(OUT/f"{name}-{width}.png"),clip={"x":0,"y":0,"width":width,"height":190})
    except Exception as e:
     print(json.dumps({"name":name,"width":width,"error":str(e)}),flush=True)
    finally: await p.close()
   await asyncio.gather(*(inspect(n,u) for n,u in URLS.items()))
   await ctx.close()
  await b.close()
asyncio.run(main())
