(() => {
  const primarySlot = document.getElementById('homepage-advertisement');
  if (!primarySlot || primarySlot.dataset.openrocketsPromotion) return;

  // The network stays disconnected until Adsterra confirms the requested category restrictions.
  const promotions = [
    [
      "homepage-advertisement",
      "OpenRockets Press",
      "Publish a research project, invention, or creative work.",
      "https://press.openrockets.com/"
    ],
    [
      "maple-live-section",
      "MDN Web Docs",
      "Learn HTML, CSS, and JavaScript at your own pace.",
      "https://developer.mozilla.org/en-US/docs/Learn_web_development"
    ],
    [
      "impact-missions-section",
      "PART Telescope Initiative",
      "See how students designed an affordable radio telescope.",
      "https://part.zeroprofit.org/"
    ],
    [
      "network-security-section",
      "Hack Club",
      "Meet other teen coders and build something together.",
      "https://hackclub.com/"
    ],
    [
      "openrockets-opensource-feature",
      "OpenRockets Open Source",
      "Explore the tools and licenses behind youth-led open source.",
      "https://opensource.openrockets.com/"
    ],
    [
      "free-infrastructure-section",
      "ZeroProfit",
      "Explore resources for starting a youth-led nonprofit.",
      "https://zeroprofit.org/"
    ],
    [
      "openrockets-donates",
      "Daydream",
      "See what teen game developers built at a global game jam.",
      "https://daydream.hackclub.com/"
    ],
    [
      "blog-slider-title",
      "SCIENTEEN",
      "Read student science writing and research.",
      "https://scienteen.com/"
    ],
    [
      "licenseu18-petition",
      "OpenRockets License Library",
      "Compare licenses for sharing your code and creative work.",
      "https://about.openrockets.com/docs/licenses/about"
    ],
    [
      "license-family-section",
      "National Youth Research Journal",
      "Explore research and publishing opportunities for students.",
      "https://www.nyrj.org/"
    ],
    [
      "teen-nonprofit-forum",
      "OpenRockets Apps",
      "Explore apps and games from young developers.",
      "https://apps.openrockets.com/"
    ]
  ];

  const style = document.createElement('style');
  style.textContent = ".or-project-promotion{box-sizing:border-box;width:min(100% - 2rem,680px);margin:24px auto;padding:14px 18px;border:1px solid #d7dce5;border-radius:12px;background:#f6f8ff;color:#192136;font:inherit;text-align:left}\n.or-project-promotion p{margin:0}\n.or-project-promotion .or-promotion-label{color:#44516c;font-size:.75rem}\n.or-project-promotion a{display:inline-block;margin:3px 0;color:#2547a3;font-weight:700;text-decoration:underline;text-underline-offset:2px;overflow-wrap:anywhere}\n.or-project-promotion .or-promotion-copy{font-size:.875rem;line-height:1.45}";
  document.head.append(style);

  for (const [anchorId, name, description, url] of promotions) {
    const anchor = document.getElementById(anchorId);
    if (!anchor) continue;

    const primary = anchor === primarySlot;
    const slot = primary ? primarySlot : document.createElement('aside');
    slot.classList.add('or-project-promotion');
    slot.dataset.openrocketsPromotion = 'true';
    slot.setAttribute('aria-label', 'Promotion: ' + name);

    const label = document.createElement('p');
    label.className = 'or-promotion-label';
    label.textContent = 'Promotion';

    const link = document.createElement('a');
    link.href = url;
    link.textContent = name;

    const copy = document.createElement('p');
    copy.className = 'or-promotion-copy';
    copy.textContent = description;

    slot.replaceChildren(label, link, copy);
    if (primary) {
      slot.removeAttribute('style');
      slot.hidden = false;
    } else {
      (anchor.closest('section') || anchor).after(slot);
    }
  }
})();
