(() => {
  // Temporarily pause every placement while Adsterra reviews the site's ad restrictions.
  const deliveryPaused = true;
  if (deliveryPaused) return;

  const primarySlot = document.getElementById('homepage-advertisement');
  if (!primarySlot || primarySlot.dataset.adsterraInitialized) return;
  primarySlot.dataset.adsterraInitialized = 'true';

  const units = [
    {
      "format": "320x50",
      "anchor": "homepage-advertisement",
      "url": "https://bauval.org/22/024af405dcb2d4af2e5d497869257276",
      "width": 320,
      "config": "atOptions = {\n    'key' : '024af405dcb2d4af2e5d497869257276',\n    'format' : 'iframe',\n    'height' : 50,\n    'width' : 320,\n    'params' : {}\n  };"
    },
    {
      "format": "468x60",
      "anchor": "maple-live-section",
      "url": "https://bauval.org/22/11d1080a110803a90f3c7f0520f35227",
      "width": 468,
      "config": "atOptions = {\n    'key' : '11d1080a110803a90f3c7f0520f35227',\n    'format' : 'iframe',\n    'height' : 60,\n    'width' : 468,\n    'params' : {}\n  };"
    },
    {
      "format": "300x250",
      "anchor": "impact-missions-section",
      "url": "https://bauval.org/22/e0b65a290e1cd1a4d1e63e4bf2a99beb",
      "width": 300,
      "config": "atOptions = {\n    'key' : 'e0b65a290e1cd1a4d1e63e4bf2a99beb',\n    'format' : 'iframe',\n    'height' : 250,\n    'width' : 300,\n    'params' : {}\n  };"
    },
    {
      "format": "160x300",
      "anchor": "network-security-section",
      "url": "https://bauval.org/22/a4324f458f0c5df65b174164c6fb5392",
      "width": 160,
      "config": "atOptions = {\n    'key' : 'a4324f458f0c5df65b174164c6fb5392',\n    'format' : 'iframe',\n    'height' : 300,\n    'width' : 160,\n    'params' : {}\n  };"
    },
    {
      "format": "Native Banner",
      "anchor": "openrockets-opensource-feature",
      "url": "https://bauval.org/21/5f2d73b7042d74ec77649b69243878fa",
      "nativeId": "container-5f2d73b7042d74ec77649b69243878fa"
    },
    {
      "format": "728x90",
      "anchor": "free-infrastructure-section",
      "url": "https://bauval.org/22/420feb9701a9922cd8538546b23cea2b",
      "width": 728,
      "config": "atOptions = {\n    'key' : '420feb9701a9922cd8538546b23cea2b',\n    'format' : 'iframe',\n    'height' : 90,\n    'width' : 728,\n    'params' : {}\n  };"
    },
    {
      "format": "160x600",
      "anchor": "blog-slider-title",
      "url": "https://bauval.org/22/e057c0fd1d43114cf2c743c1829c503c",
      "width": 160,
      "config": "atOptions = {\n    'key' : 'e057c0fd1d43114cf2c743c1829c503c',\n    'format' : 'iframe',\n    'height' : 600,\n    'width' : 160,\n    'params' : {}\n  };"
    }
  ];
  const placements = new Map();
  let consentActive = false;
  let queue = Promise.resolve();

  const style = document.createElement('style');
  style.textContent = `
    [data-adsterra-placement] { display:block;min-height:1px;margin:auto;text-align:center; }
    [data-adsterra-placement][hidden] { display:none; }
    [data-adsterra-filled] { margin:24px auto; }
    [data-adsterra-label] { margin:0 0 4px;color:#485467;font-size:12px; }
    @media (max-width:487px) { [data-adsterra-placement="468x60"] { display:none; } }
    @media (max-width:747px) { [data-adsterra-placement="728x90"] { display:none; } }
  `;
  document.head.append(style);

  function mountAd(placement) {
    const {slot, unit} = placement;
    if (placements.get(slot) !== placement) return;

    const label = document.createElement('p');
    label.dataset.adsterraLabel = '';
    label.textContent = 'Advertisement';
    label.hidden = true;
    const content = document.createElement('div');
    content.style.cssText = 'margin:auto;max-width:100%';
    if (unit.width) content.style.width = unit.width + 'px';
    slot.append(label, content);

    const watcher = new MutationObserver(() => {
      if (content.querySelector('iframe, img, a[href]')) {
        slot.dataset.adsterraFilled = '';
        label.hidden = false;
        watcher.disconnect();
      }
    });
    placement.watcher = watcher;
    watcher.observe(content, {childList: true, subtree: true});

    if (unit.nativeId) {
      const target = document.createElement('div');
      target.id = unit.nativeId;
      content.append(target);
    } else {
      const config = document.createElement('script');
      config.textContent = unit.config;
      content.append(config);
    }
    const loader = document.createElement('script');
    loader.setAttribute('data-cfasync', 'false');
    loader.async = Boolean(unit.nativeId);
    if (unit.nativeId) loader.fetchPriority = 'high';
    loader.src = unit.url;

    // Load display tags in order because Adsterra's display snippets share atOptions.
    return new Promise(resolve => {
      loader.addEventListener('load', resolve, {once: true});
      loader.addEventListener('error', () => {
        watcher.disconnect();
        slot.replaceChildren();
        delete slot.dataset.adsterraFilled;
        resolve();
      }, {once: true});
      content.append(loader);
    });
  }

  const visibility = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      visibility.unobserve(entry.target);
      const placement = placements.get(entry.target);
      if (placement) queue = queue.then(() => mountAd(placement));
    }
  }, {rootMargin: '300px 0px'});

  function updateConsent() {
    const consent = window.cookieconsent?.cookieConsentObject?.userConsent;
    const allowed = consent?.userAccepted === true && consent.acceptedLevels?.targeting === true;
    if (allowed === consentActive) return;
    consentActive = allowed;

    if (!allowed) {
      visibility.disconnect();
      for (const [slot, placement] of placements) {
        placement.watcher?.disconnect();
        if (slot === primarySlot) {
          slot.hidden = true;
          slot.replaceChildren();
          delete slot.dataset.adsterraFilled;
        } else {
          slot.remove();
        }
      }
      placements.clear();
      return;
    }

    for (const unit of units) {
      const anchor = document.getElementById(unit.anchor);
      if (!anchor) continue;
      const slot = anchor === primarySlot ? primarySlot : document.createElement('aside');
      slot.dataset.adsterraPlacement = unit.format;
      slot.setAttribute('aria-label', 'Advertisement');
      slot.removeAttribute('style');
      slot.hidden = false;
      slot.replaceChildren();
      if (slot !== primarySlot) (anchor.closest('section') || anchor).after(slot);
      placements.set(slot, {slot, unit});
      visibility.observe(slot);
    }
  }

  document.addEventListener('cc_userConsentSaved', updateConsent);
  updateConsent();
})();
