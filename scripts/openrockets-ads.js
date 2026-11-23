(() => {
  'use strict';

  const SUPABASE_URL = 'https://ahkfuaaryzmcmoarxraq.supabase.co';
  const SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_u5nnlGCzUOpDdCtBrbmRtw_doE4Osgl';
  const OPENROCKETS_ADS_LOGO = 'https://openrockets.com/v/89769876987987.png';
  const WHY_LINK = 'https://zeroprofit.org/ads';
  const slots = Array.from(document.querySelectorAll('[data-openrockets-ad]'));
  if (!slots.length) return;

  let dropdownSequence = 0;

  function safeWebUrl(value) {
    if (typeof value !== 'string' || !value.trim()) return null;
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
    } catch {
      return null;
    }
  }

  function normalizeAd(row) {
    const imageUrl = safeWebUrl(row.image_url);
    const linkUrl = safeWebUrl(row.link_url);
    if (!imageUrl || !linkUrl) return null;

    return {
      imageUrl,
      linkUrl,
      altText: String(row.alt_text || row.nonprofit_name || 'Nonprofit advertisement'),
    };
  }

  function createAdContents(currentAd) {
    const container = document.createElement('div');
    container.className = 'or-ad-container';

    const link = document.createElement('a');
    link.href = currentAd.linkUrl;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.className = 'or-ad-link';

    const image = document.createElement('img');
    image.src = currentAd.imageUrl;
    image.alt = currentAd.altText;
    image.className = 'or-ad-image';
    image.loading = 'lazy';
    image.decoding = 'async';
    image.referrerPolicy = 'no-referrer';
    link.append(image);

    const badge = document.createElement('div');
    badge.className = 'or-ad-badge-container';

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'or-ad-badge-toggle';
    toggle.setAttribute('aria-label', 'About OpenRockets Ads');
    toggle.setAttribute('aria-expanded', 'false');
    const descriptionId = 'or-ad-why-' + (++dropdownSequence);
    toggle.setAttribute('aria-controls', descriptionId);

    const logo = document.createElement('img');
    logo.src = OPENROCKETS_ADS_LOGO;
    logo.alt = 'OpenRockets Ads';
    logo.className = 'or-ad-badge-logo';
    toggle.append(logo);

    const separator = document.createElement('span');
    separator.className = 'or-ad-badge-separator';
    separator.textContent = '•';
    toggle.append(separator);

    const why = document.createElement('span');
    why.className = 'or-ad-badge-text-why';
    why.textContent = 'Why?';
    toggle.append(why);

    const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    chevron.setAttribute('viewBox', '0 0 20 20');
    chevron.setAttribute('fill', 'currentColor');
    chevron.setAttribute('aria-hidden', 'true');
    chevron.classList.add('or-ad-badge-chevron');
    const chevronPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    chevronPath.setAttribute('fill-rule', 'evenodd');
    chevronPath.setAttribute('clip-rule', 'evenodd');
    chevronPath.setAttribute('d', 'M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z');
    chevron.append(chevronPath);
    toggle.append(chevron);

    const dropdown = document.createElement('div');
    dropdown.className = 'or-ad-dropdown';
    dropdown.id = descriptionId;
    dropdown.hidden = true;

    const explanation = document.createElement('p');
    explanation.append(document.createTextNode(
      'OpenRockets ads is an advertisement network for nonprofits and communities started by people under the age of 20. We provide them the ability to post ads for 100% free with a rigorous moderation process, abuse protection, and analytics for the best visibility.'
    ));
    explanation.append(document.createElement('br'), document.createElement('br'));
    explanation.append(document.createTextNode(
      'You are seeing this ad because you are using a product or service developed by OpenRockets Inc.'
    ));
    explanation.append(document.createElement('br'), document.createElement('br'));

    const learnMore = document.createElement('a');
    learnMore.href = WHY_LINK;
    learnMore.target = '_blank';
    learnMore.rel = 'noopener noreferrer';
    learnMore.textContent = 'Learn more at zeroprofit.org/ads';
    explanation.append(learnMore);
    dropdown.append(explanation);

    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(expanded));
      dropdown.hidden = !expanded;
      chevron.classList.toggle('expanded', expanded);
    });

    badge.append(toggle, dropdown);
    container.append(link, badge);
    return container;
  }

  async function loadAcceptedAds() {
    const endpoint = new URL('/rest/v1/free_ads', SUPABASE_URL);
    endpoint.search = new URLSearchParams({
      select: 'nonprofit_name,image_url,link_url,alt_text',
      status: 'eq.accepted',
      order: 'created_at.desc',
      limit: '100',
    }).toString();

    const response = await fetch(endpoint, {
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        Accept: 'application/json',
      },
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
    });
    if (!response.ok) throw new Error('Ad feed request failed: ' + response.status);

    const rows = await response.json();
    if (!Array.isArray(rows)) return [];
    const ads = rows.map(normalizeAd).filter(Boolean);
    for (let index = ads.length - 1; index > 0; index -= 1) {
      const other = Math.floor(Math.random() * (index + 1));
      [ads[index], ads[other]] = [ads[other], ads[index]];
    }
    return ads;
  }

  function fillSlot(slot, ads, startIndex, loading = 'lazy') {
    let attempts = 0;
    function renderNext() {
      if (attempts >= ads.length) {
        slot.hidden = true;
        slot.replaceChildren();
        return;
      }
      const ad = ads[(startIndex + attempts) % ads.length];
      attempts += 1;
      const card = createAdContents(ad);
      const image = card.querySelector('.or-ad-image');
      image.loading = loading;
      image.addEventListener('error', renderNext, { once: true });
      slot.replaceChildren(card);
      slot.hidden = false;
    }
    renderNext();
  }

  function setupVignette(ads) {
    const dialog = document.createElement('dialog');
    dialog.className = 'or-vignette-dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-label', 'Advertisement');

    const closeRow = document.createElement('div');
    closeRow.className = 'or-vignette-close-row';

    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'or-vignette-close';
    closeButton.setAttribute('aria-label', 'Close advertisement');

    const closeText = document.createElement('span');
    closeText.textContent = 'Close';
    closeButton.append(closeText);

    const closeIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    closeIcon.setAttribute('viewBox', '0 0 24 24');
    closeIcon.setAttribute('fill', 'none');
    closeIcon.setAttribute('stroke', 'currentColor');
    closeIcon.setAttribute('stroke-width', '2');
    closeIcon.setAttribute('aria-hidden', 'true');
    const closePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    closePath.setAttribute('stroke-linecap', 'round');
    closePath.setAttribute('stroke-linejoin', 'round');
    closePath.setAttribute('d', 'M6 6l12 12M18 6 6 18');
    closeIcon.append(closePath);
    closeButton.append(closeIcon);
    closeRow.append(closeButton);

    const scroll = document.createElement('div');
    scroll.className = 'or-vignette-scroll';

    const adPanel = document.createElement('section');
    adPanel.className = 'or-ad-wrapper';
    adPanel.setAttribute('aria-label', 'Advertisement');
    adPanel.hidden = true;
    fillSlot(adPanel, ads, slots.length, 'eager');
    scroll.append(adPanel);

    dialog.append(closeRow, scroll);
    document.body.append(dialog);

    let pendingTarget = null;
    let clickCount = 0;
    try {
      clickCount = Number.parseInt(sessionStorage.getItem('vignette_click_count') || '0', 10) || 0;
    } catch {
      // Keep the count in memory if session storage is unavailable.
    }

    function continueToLink() {
      const target = pendingTarget;
      pendingTarget = null;
      dialog.close();
      if (!target) return;
      if (target.newTab) {
        window.open(target.href, '_blank', 'noopener,noreferrer');
      } else {
        window.location.assign(target.href);
      }
    }

    closeButton.addEventListener('click', continueToLink);
    dialog.addEventListener('cancel', event => {
      event.preventDefault();
      continueToLink();
    });
    dialog.addEventListener('click', event => {
      if (event.target === dialog) continueToLink();
    });

    document.addEventListener('click', event => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey ||
          event.shiftKey || event.altKey || dialog.open) return;
      const clicked = event.target instanceof Element ? event.target : null;
      const link = clicked?.closest('a[href]');
      if (!link || link.closest('[role="dialog"], [data-openrockets-ad]') ||
          link.hasAttribute('download') || link.getAttribute('href').startsWith('#')) return;

      const url = new URL(link.href, location.href);
      if (!['http:', 'https:'].includes(url.protocol)) return;
      if (url.origin === location.origin && url.pathname === location.pathname &&
          url.search === location.search) return;
      const target = (link.getAttribute('target') || '_self').toLowerCase();
      if (target !== '_blank' && target !== '_self') return;

      clickCount += 1;
      try {
        sessionStorage.setItem('vignette_click_count', String(clickCount));
      } catch {
        // The in-memory counter already includes this click.
      }
      const image = adPanel.querySelector('.or-ad-image');
      if (clickCount % 2 !== 0 || !image?.complete || !image.naturalWidth) return;

      try {
        dialog.showModal();
      } catch {
        return;
      }
      pendingTarget = { href: url.href, newTab: target === '_blank' };
      event.preventDefault();
      event.stopPropagation();
    }, { capture: true });
  }

  loadAcceptedAds()
    .then(ads => {
      if (!ads.length) return;
      slots.forEach((slot, index) => fillSlot(slot, ads, index));
      setupVignette(ads);
    })
    .catch(error => {
      console.warn('[OpenRockets Ads] Could not load accepted ads.', error);
    });
})();
