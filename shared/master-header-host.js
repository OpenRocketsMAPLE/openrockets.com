(() => {
  const frame=document.getElementById("main-header");
  if(!(frame instanceof HTMLIFrameElement))return;
  const origin=new URL(frame.src).origin;
  const apply=event=>{
    if(event.origin!==origin||event.source!==frame.contentWindow||event.data?.type!=="openrockets-master-header-height-v2")return;
    const height=event.data.height;
    if(!Number.isFinite(height)||height<20||height>800)return;
    document.documentElement.style.setProperty("--openrockets-master-height",Math.ceil(height)+"px");
  };
  const measure=()=>frame.contentWindow?.postMessage({type:"openrockets-master-header-measure-v2"},origin);
  window.addEventListener("message",apply);
  frame.addEventListener("load",measure);
  measure();
})();
