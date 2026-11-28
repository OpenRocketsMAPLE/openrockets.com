(() => {
const header=document.getElementById("main-header");
const toggle=document.getElementById("or-mobile-nav-toggle");
if(!header||!toggle)return;
const setOpen=open=>{toggle.setAttribute("aria-expanded",String(open));toggle.setAttribute("aria-label",open?"Collapse navigation":"Expand navigation");};
toggle.addEventListener("click",()=>setOpen(toggle.getAttribute("aria-expanded")!=="true"));
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&toggle.getAttribute("aria-expanded")==="true"){setOpen(false);toggle.focus();}});
window.addEventListener("resize",()=>{if(innerWidth>980)setOpen(false);},{passive:true});
const update=()=>document.documentElement.style.setProperty("--openrockets-master-height",Math.ceil(header.getBoundingClientRect().height)+"px");
if("ResizeObserver" in window)new ResizeObserver(update).observe(header);
update();
})();