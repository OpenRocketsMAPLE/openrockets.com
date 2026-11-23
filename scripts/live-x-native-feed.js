(() => {
  const WIDGET_ID = "739491f1-b20f-438a-837a-73fb487ee5f2";
  const MAX_POSTS = 100;
  const INITIAL_PER_SECTION = 4;
  const LOAD_MORE_STEP = 4;
  const MIN_WORDS = 6;
  const CORE_URL = "https://core.service.elfsight.com";
  const DATA_URL = "https://widget-data.service.elfsight.com";

  const grids = Array.from(document.querySelectorAll(".or-native-x-grid[data-or-x-grid]"));
  if (!grids.length) return;

  const meaningfulWordCount = (text) =>
    String(text || "")
      .replace(/<[^>]*>/g, " ")
      .replace(/&(?:#\d+|#x[0-9a-f]+|[a-z][a-z0-9]+);/gi, " ")
      .replace(/https?:\/\/\S+/g, " ")
      .replace(/[@#][\p{L}\p{N}_-]+/gu, " ")
      .match(/[\p{L}\p{N}][\p{L}\p{N}'’_-]*/gu)?.length || 0;

  const qualifies = (post) => meaningfulWordCount(post?.caption) >= MIN_WORDS;

  const uniquePosts = (posts) => {
    const seen = new Set();
    return (posts || []).filter((post) => {
      const id = String(post?.vendorId || post?.id || "");
      if (!id || seen.has(id) || !qualifies(post)) return false;
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

    const badge = document.createElement("span");
    badge.className = "or-native-x-verified-badge";
    badge.setAttribute("aria-label", "Verified");
    badge.innerHTML = '<svg viewBox="0 0 22 22" aria-hidden="true"><path fill="currentColor" d="M20.396 11c0-1.278-1.006-2.282-1.906-3.09.098-1.206-.175-2.566-1.128-3.518-.952-.952-2.31-1.225-3.516-1.127C13.036 2.366 12.033 1.36 10.754 1.36S8.472 2.366 7.664 3.265c-1.207-.098-2.566.175-3.518 1.127-.952.952-1.225 2.312-1.127 3.518-.9.808-1.906 1.812-1.906 3.09s1.006 2.282 1.906 3.09c-.098 1.206.175 2.566 1.127 3.518.952.952 2.311 1.225 3.518 1.127.808.9 1.812 1.905 3.09 1.905s2.282-1.006 3.092-1.905c1.206.098 2.564-.175 3.516-1.127.953-.952 1.226-2.312 1.128-3.518.9-.808 1.906-1.812 1.906-3.09Zm-11.3 4.047-3.11-3.11 1.414-1.414 1.696 1.696 4.41-4.41 1.414 1.414-5.824 5.824Z"/></svg>';

    const dateMask = document.createElement("span");
    dateMask.className = "or-native-x-date-mask";
    dateMask.setAttribute("aria-hidden", "true");

    slot.append(quote, badge, dateMask);
    return slot;
  };

  const ensureShowMore = (placement, onClick) => {
    let shell = placement.querySelector(".or-native-x-more-shell");
    if (!shell) {
      shell = document.createElement("div");
      shell.className = "or-native-x-more-shell";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "or-native-x-show-more";
      button.textContent = "Show more";
      button.addEventListener("click", onClick);

      shell.appendChild(button);
      placement.appendChild(shell);
    }
    return shell;
  };

  const loadTwitterRenderer = async () => {
    if (window.twttr?.widgets?.load) return;

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
  };

  const renderGrid = async (grid) => {
    await loadTwitterRenderer();
    if (window.twttr?.widgets?.load) {
      await window.twttr.widgets.load(grid);
    }
  };

  const distribute = async (posts) => {
    const groups = Array.from({ length: grids.length }, () => []);
    posts.forEach((post, index) => groups[index % grids.length].push(post));

    await Promise.all(grids.map(async (grid, index) => {
      grid.replaceChildren();
      const placement = grid.closest(".or-native-x-placement");
      if (!placement) return;

      placement.querySelector(".or-native-x-more-shell")?.remove();

      const group = groups[index];
      let visible = 0;

      const append = async (amount) => {
        const next = group.slice(visible, visible + amount);
        if (!next.length) return;

        const fragment = document.createDocumentFragment();
        next.forEach((post) => {
          const embed = makeEmbed(post);
          if (embed) fragment.appendChild(embed);
        });
        grid.appendChild(fragment);
        visible += next.length;

        await renderGrid(grid);

        const shell = placement.querySelector(".or-native-x-more-shell");
        if (visible >= group.length) {
          shell?.remove();
        }
      };

      if (group.length > INITIAL_PER_SECTION) {
        ensureShowMore(placement, () => append(LOAD_MORE_STEP));
      }

      await append(INITIAL_PER_SECTION);
    }));
  };

  (async () => {
    let posts = [];
    try {
      posts = await fetchLivePosts();
    } catch (error) {
      console.warn("Live X feed unavailable; using cached feed.", error);
      posts = await fetchCachedPosts();
    }

    await distribute(posts);
  })();
})();
