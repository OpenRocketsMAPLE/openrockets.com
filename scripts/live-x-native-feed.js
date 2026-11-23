(() => {
  const WIDGET_ID = "739491f1-b20f-438a-837a-73fb487ee5f2";
  const MAX_POSTS = 100;
  const CORE_URL = "https://core.service.elfsight.com";
  const DATA_URL = "https://widget-data.service.elfsight.com";

  const grids = Array.from(document.querySelectorAll(".or-native-x-grid[data-or-x-grid]"));
  if (!grids.length) return;

  const uniquePosts = (posts) => {
    const seen = new Set();
    return (posts || []).filter((post) => {
      const id = String(post?.vendorId || post?.id || "");
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    }).slice(0, MAX_POSTS);
  };

  const postUrl = (post) => {
    const direct = post?.link;
    if (direct) return String(direct).replace("https://www.x.com/", "https://x.com/");
    const user = post?.author?.username || "maplelicense";
    const id = post?.vendorId || post?.id;
    return id ? `https://x.com/${user}/status/${id}` : "";
  };

  const loadBoot = async () => {
    const params = new URLSearchParams({
      w: WIDGET_ID,
      page: window.location.origin + window.location.pathname
    });
    const response = await fetch(`${CORE_URL}/p/boot/?${params.toString()}`, {
      credentials: "include",
      mode: "cors",
      cache: "no-store"
    });
    if (!response.ok) throw new Error(`Elfsight boot failed: ${response.status}`);
    const json = await response.json();
    const widget = json?.data?.widgets?.[WIDGET_ID]?.data;
    if (!widget?.public_widget_token) throw new Error("Elfsight public widget token unavailable");
    return widget;
  };

  const fetchLivePosts = async () => {
    const widget = await loadBoot();
    const account = widget?.settings?.account;
    if (!account?.pid) throw new Error("MAPLE X source PID unavailable");

    const allowed = Array.isArray(widget?.settings?.filterByTypes)
      ? widget.settings.filterByTypes
      : ["reply", "repost", "common"];
    const filters = ["reply", "repost", "common"]
      .filter((type) => !allowed.includes(type))
      .map((post_type) => ({ type: "exclude", post_type }));

    const source = encodeURIComponent(JSON.stringify({ pid: account.pid, filters }));
    const url = `${DATA_URL}/api/posts?sources[]=${source}&sort=date&limit=${MAX_POSTS}&offset=0`;
    const response = await fetch(url, {
      mode: "cors",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        "x-widget-token": widget.public_widget_token
      }
    });
    if (!response.ok) throw new Error(`Live X feed failed: ${response.status}`);
    const json = await response.json();
    if (json?.code !== 200 || !Array.isArray(json?.payload)) {
      throw new Error("Live X feed returned invalid data");
    }
    return uniquePosts(json.payload);
  };

  const fetchCachedPosts = async () => {
    for (const url of [
      `data/x-feed.json?v=${Date.now()}`,
      "vendor/widget-data.service.elfsight.com/cd83495a57827136__posts.json"
    ]) {
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) continue;
        const json = await response.json();
        const posts = Array.isArray(json?.posts) ? json.posts : json?.payload;
        const clean = uniquePosts(posts);
        if (clean.length) return clean;
      } catch (_) {}
    }
    return [];
  };

  const makeEmbed = (post) => {
    const url = postUrl(post);
    if (!url) return null;

    const slot = document.createElement("div");
    slot.className = "or-native-x-slot";

    const quote = document.createElement("blockquote");
    quote.className = "twitter-tweet";
    quote.setAttribute("data-theme", "light");
    quote.setAttribute("data-dnt", "true");
    quote.setAttribute("data-conversation", "none");

    const link = document.createElement("a");
    link.href = url;
    link.textContent = "";
    quote.appendChild(link);
    slot.appendChild(quote);
    return slot;
  };

  const distribute = (posts) => {
    grids.forEach((grid) => grid.replaceChildren());
    if (!posts.length) return;

    const base = Math.floor(posts.length / grids.length);
    let remainder = posts.length % grids.length;
    let cursor = 0;

    grids.forEach((grid) => {
      const count = base + (remainder-- > 0 ? 1 : 0);
      const fragment = document.createDocumentFragment();
      posts.slice(cursor, cursor + count).forEach((post) => {
        const embed = makeEmbed(post);
        if (embed) fragment.appendChild(embed);
      });
      cursor += count;
      grid.appendChild(fragment);
    });
  };

  const renderNativeX = async () => {
    if (window.twttr?.widgets?.load) {
      await window.twttr.widgets.load();
      return;
    }

    let script = document.querySelector('script[data-or-x-widgets="true"]');
    if (!script) {
      script = document.createElement("script");
      script.src = "https://platform.twitter.com/widgets.js";
      script.async = true;
      script.charset = "utf-8";
      script.dataset.orXWidgets = "true";
      document.head.appendChild(script);
    }

    await new Promise((resolve) => {
      if (window.twttr?.widgets?.load) return resolve();
      script.addEventListener("load", resolve, { once: true });
      script.addEventListener("error", resolve, { once: true });
      setTimeout(resolve, 8000);
    });

    if (window.twttr?.widgets?.load) {
      await window.twttr.widgets.load();
    }
  };

  (async () => {
    let posts = [];
    try {
      posts = await fetchLivePosts();
    } catch (error) {
      console.warn("Live X feed unavailable; using cached feed.", error);
      posts = await fetchCachedPosts();
    }

    distribute(posts);
    await renderNativeX();
  })();
})();
