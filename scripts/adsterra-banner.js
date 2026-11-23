(() => {
  const slot = document.querySelector('[data-openrockets-ad]');
  if (!slot) return;

  const productIds = slot.dataset.adProductIds;
  const productId = new URLSearchParams(window.location.search).get('id');
  if (productIds && !productIds.split(',').includes(productId)) return;

  const bannerDocument = "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>Advertisement</title><body style=\"margin:0\"><script>\n  atOptions = {\n    'key' : '024af405dcb2d4af2e5d497869257276',\n    'format' : 'iframe',\n    'height' : 50,\n    'width' : 320,\n    'params' : {}\n  };\n</script>\n<script data-cfasync=\"false\" src=\"https://bauval.org/22/024af405dcb2d4af2e5d497869257276\"></script></body></html>";
  function updateBanner() {
    const consent = window.cookieconsent?.cookieConsentObject?.userConsent;
    const allowed = consent?.userAccepted === true && consent.acceptedLevels?.targeting === true;
    const existingFrame = slot.querySelector('iframe');

    if (allowed && !existingFrame) {
      const frame = document.createElement('iframe');
      frame.title = 'Advertisement from Adsterra';
      frame.width = '320';
      frame.height = '50';
      frame.loading = 'lazy';
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      frame.setAttribute('sandbox', 'allow-scripts allow-popups allow-popups-to-escape-sandbox');
      frame.style.cssText = 'display:block;margin:auto;max-width:100%;border:0';
      frame.srcdoc = bannerDocument;
      slot.append(frame);
    } else if (!allowed && existingFrame) {
      existingFrame.remove();
    }
    slot.hidden = !allowed;
  }

  document.addEventListener('cc_userConsentSaved', updateBanner);
  updateBanner();
})();
