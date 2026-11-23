(() => {
  const slot = document.querySelector('[data-openrockets-ad]');
  if (!slot) return;

  const productIds = slot.dataset.adProductIds;
  const productId = new URLSearchParams(window.location.search).get('id');
  if (productIds && !productIds.split(',').includes(productId)) return;

  let mount;
  let observer;

  function removeBanner() {
    observer?.disconnect();
    mount?.remove();
    mount = undefined;
    slot.hidden = true;
  }

  function updateBanner() {
    const consent = window.cookieconsent?.cookieConsentObject?.userConsent;
    const allowed = consent?.userAccepted === true && consent.acceptedLevels?.targeting === true;
    if (!allowed) {
      removeBanner();
      return;
    }
    if (mount) return;

    const container = document.createElement('div');
    container.style.cssText = 'width:320px;max-width:100%;margin:auto';
    mount = container;

    observer = new MutationObserver(() => {
      if (container.querySelector('iframe')) slot.hidden = false;
    });
    observer.observe(container, {childList: true, subtree: true});

    const config = document.createElement('script');
    config.textContent = "\n  atOptions = {\n    'key' : '024af405dcb2d4af2e5d497869257276',\n    'format' : 'iframe',\n    'height' : 50,\n    'width' : 320,\n    'params' : {}\n  };\n";
    const loader = document.createElement('script');
    loader.async = false;
    loader.setAttribute('data-cfasync', 'false');
    loader.src = "https://bauval.org/22/024af405dcb2d4af2e5d497869257276";
    loader.addEventListener('error', () => {
      if (mount === container) removeBanner();
    }, {once: true});

    slot.append(container);
    container.append(config, loader);
  }

  document.addEventListener('cc_userConsentSaved', updateBanner);
  updateBanner();
})();
