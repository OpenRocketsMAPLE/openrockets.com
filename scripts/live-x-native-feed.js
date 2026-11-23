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
      throw new Error("Live Twitter feed returned invalid data");
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

  const svg = (path, className = "") => {
    const ns = "http://www.w3.org/2000/svg";
    const node = document.createElementNS(ns, "svg");
    node.setAttribute("viewBox", "0 0 24 24");
    node.setAttribute("aria-hidden", "true");
    if (className) node.setAttribute("class", className);
    const p = document.createElementNS(ns, "path");
    p.setAttribute("d", path);
    p.setAttribute("fill", "currentColor");
    node.appendChild(p);
    return node;
  };

  const verifiedIcon = () => {
    const span = document.createElement("span");
    span.className = "or-x-inline-verified";
    span.setAttribute("aria-label", "Verified");
    span.appendChild(svg("M20.396 11c0-1.278-1.006-2.282-1.906-3.09.098-1.206-.175-2.566-1.128-3.518-.952-.952-2.31-1.225-3.516-1.127C13.036 2.366 12.033 1.36 10.754 1.36S8.472 2.366 7.664 3.265c-1.207-.098-2.566.175-3.518 1.127-.952.952-1.225 2.312-1.127 3.518-.9.808-1.906 1.812-1.906 3.09s1.006 2.282 1.906 3.09c-.098 1.206.175 2.566 1.127 3.518.952.952 2.311 1.225 3.518 1.127.808.9 1.812 1.905 3.09 1.905s2.282-1.006 3.092-1.905c1.206.098 2.564-.175 3.516-1.127.953-.952 1.226-2.312 1.128-3.518.9-.808 1.906-1.812 1.906-3.09Zm-11.3 4.047-3.11-3.11 1.414-1.414 1.696 1.696 4.41-4.41 1.414 1.414-5.824 5.824Z"));
    return span;
  };

  const linkifyCaption = (text) => {
    const fragment = document.createDocumentFragment();
    const cleaned = String(text || "").replace(/https:\/\/t\.co\/\S+/g, "").trim();
    const pattern = /(@[A-Za-z0-9_]+|https?:\/\/\S+)/g;
    let last = 0;

    cleaned.replace(pattern, (match, _group, offset) => {
      if (offset > last) fragment.append(document.createTextNode(cleaned.slice(last, offset)));

      const anchor = document.createElement("a");
      anchor.className = "or-x-inline-link";
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = match;
      anchor.href = match.startsWith("@") ? `https://x.com/${match.slice(1)}` : match;
      fragment.append(anchor);
      last = offset + match.length;
      return match;
    });

    if (last < cleaned.length) fragment.append(document.createTextNode(cleaned.slice(last)));
    return fragment;
  };

  const mediaUrl = (media) =>
    media?.standard?.url || media?.original?.url || media?.thumbnail?.url || null;

  const buildAuthor = (author, compact = false) => {
    const row = document.createElement("div");
    row.className = compact ? "or-x-author or-x-author--compact" : "or-x-author";

    if (author?.profilePictureUrl) {
      const avatar = document.createElement("img");
      avatar.className = "or-x-avatar";
      avatar.src = author.profilePictureUrl;
      avatar.alt = "";
      avatar.loading = "lazy";
      avatar.decoding = "async";
      row.appendChild(avatar);
    }

    const identity = document.createElement("div");
    identity.className = "or-x-identity";

    const nameLine = document.createElement("div");
    nameLine.className = "or-x-name-line";

    const name = document.createElement("strong");
    name.className = "or-x-display-name";
    name.textContent = author?.name || author?.username || "OpenRockets";
    nameLine.append(name, verifiedIcon());

    const handleLine = document.createElement("div");
    handleLine.className = "or-x-handle-line";

    const handle = document.createElement("span");
    handle.className = "or-x-handle";
    handle.textContent = `@${author?.username || "openrockets"}`;
    handleLine.appendChild(handle);

    if (!compact) {
      const separator = document.createElement("span");
      separator.className = "or-x-handle-separator";
      separator.textContent = "·";

      const follow = document.createElement("a");
      follow.className = "or-x-follow";
      follow.href = `https://x.com/${author?.username || "openrockets"}`;
      follow.target = "_blank";
      follow.rel = "noopener noreferrer";
      follow.textContent = "Follow";

      handleLine.append(separator, follow);
    }

    identity.append(nameLine, handleLine);
    row.appendChild(identity);
    return row;
  };

  const buildQuotedPost = (quoted) => {
    if (!quoted) return null;

    const box = document.createElement("a");
    box.className = "or-x-quote";
    box.href = postUrl(quoted);
    box.target = "_blank";
    box.rel = "noopener noreferrer";

    box.appendChild(buildAuthor(quoted.author, true));

    if (quoted.caption) {
      const copy = document.createElement("div");
      copy.className = "or-x-quote-copy";
      copy.appendChild(linkifyCaption(quoted.caption));
      box.appendChild(copy);
    }

    const firstMedia = (quoted.media || []).map(mediaUrl).find(Boolean);
    if (firstMedia) {
      const img = document.createElement("img");
      img.className = "or-x-quote-media";
      img.src = firstMedia;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      box.appendChild(img);
    }

    return box;
  };

  const buildPost = (post) => {
    const url = postUrl(post);
    if (!url) return null;

    const card = document.createElement("article");
    card.className = "or-x-card";

    const head = document.createElement("div");
    head.className = "or-x-card-head";
    head.appendChild(buildAuthor(post.author));

    const twitter = document.createElement("a");
    twitter.className = "or-twitter-brand";
    twitter.href = url;
    twitter.target = "_blank";
    twitter.rel = "noopener noreferrer";
    twitter.setAttribute("aria-label", "Open this post on Twitter");
    const twitterIcon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    twitterIcon.setAttribute("viewBox", "0 0 16 16");
    twitterIcon.setAttribute("aria-hidden", "true");
    twitterIcon.setAttribute("focusable", "false");
    const twitterPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    twitterPath.setAttribute("d", "M5.026 15c6.038 0 9.341-5.003 9.341-9.334 0-.14 0-.282-.006-.422A6.685 6.685 0 0 0 16 3.542a6.658 6.658 0 0 1-1.889.518 3.301 3.301 0 0 0 1.447-1.817 6.533 6.533 0 0 1-2.087.793A3.286 3.286 0 0 0 7.875 6.03a9.325 9.325 0 0 1-6.767-3.429 3.289 3.289 0 0 0 1.018 4.382A3.323 3.323 0 0 1 .64 6.575v.045a3.288 3.288 0 0 0 2.632 3.218 3.203 3.203 0 0 1-.865.115 3.23 3.23 0 0 1-.614-.057 3.283 3.283 0 0 0 3.067 2.28A6.588 6.588 0 0 1 .78 13.58a6.32 6.32 0 0 1-.78-.045A9.344 9.344 0 0 0 5.026 15");
    twitterIcon.appendChild(twitterPath);
    twitter.appendChild(twitterIcon);
    head.appendChild(twitter);
    card.appendChild(head);

    const bodyLink = document.createElement("a");
    bodyLink.className = "or-x-card-body";
    bodyLink.href = url;
    bodyLink.target = "_blank";
    bodyLink.rel = "noopener noreferrer";

    const text = document.createElement("div");
    text.className = "or-x-card-copy";
    text.appendChild(linkifyCaption(post.caption));
    bodyLink.appendChild(text);

    const quoted = buildQuotedPost(post.extra?.quoted);
    if (quoted) bodyLink.appendChild(quoted);

    const firstMedia = (post.media || []).map(mediaUrl).find(Boolean);
    if (firstMedia) {
      const img = document.createElement("img");
      img.className = "or-x-media";
      img.src = firstMedia;
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      bodyLink.appendChild(img);
    }

    card.appendChild(bodyLink);

    const actions = document.createElement("div");
    actions.className = "or-x-actions";

    const likes = document.createElement("span");
    likes.className = "or-x-action or-x-action--likes";
    likes.appendChild(svg("M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"));
    const likeCount = document.createElement("span");
    likeCount.textContent = String(post.likesCount || 0);
    likes.appendChild(likeCount);

    const replies = document.createElement("a");
    replies.className = "or-x-action";
    replies.href = url;
    replies.target = "_blank";
    replies.rel = "noopener noreferrer";
    replies.appendChild(svg("M20 2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4l4 4 4-4h4a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z"));
    const replyText = document.createElement("span");
    replyText.textContent = "Reply";
    replies.appendChild(replyText);

    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "or-x-action or-x-copy";
    copy.appendChild(svg("M3.9 12c0-2.8 2.3-5.1 5.1-5.1h3v2H9a3.1 3.1 0 1 0 0 6.2h3v2H9A5.1 5.1 0 0 1 3.9 12Zm6.1 1v-2h4v2h-4Zm5-6.1h-3v-2h3a5.1 5.1 0 0 1 0 10.2h-3v-2h3a3.1 3.1 0 1 0 0-6.2Z"));
    const copyText = document.createElement("span");
    copyText.textContent = "Copy link to post";
    copy.appendChild(copyText);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(url);
        copyText.textContent = "Copied";
        setTimeout(() => { copyText.textContent = "Copy link to post"; }, 1400);
      } catch (_) {
        window.open(url, "_blank", "noopener,noreferrer");
      }
    });

    actions.append(likes, replies, copy);
    card.appendChild(actions);

    const more = document.createElement("a");
    more.className = "or-x-read-more";
    more.href = url;
    more.target = "_blank";
    more.rel = "noopener noreferrer";
    more.textContent = "Read more on Twitter";
    card.appendChild(more);

    return card;
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

  const distribute = (posts) => {
    const groups = Array.from({ length: grids.length }, () => []);
    posts.forEach((post, index) => groups[index % grids.length].push(post));

    grids.forEach((grid, index) => {
      grid.replaceChildren();
      const placement = grid.closest(".or-native-x-placement");
      if (!placement) return;
      placement.querySelector(".or-native-x-more-shell")?.remove();

      const group = groups[index];
      let visible = 0;

      const append = (amount) => {
        const next = group.slice(visible, visible + amount);
        if (!next.length) return;

        const fragment = document.createDocumentFragment();
        next.forEach((post) => {
          const card = buildPost(post);
          if (card) {
            const slot = document.createElement("div");
            slot.className = "or-native-x-slot";
            slot.appendChild(card);
            fragment.appendChild(slot);
          }
        });

        grid.appendChild(fragment);
        visible += next.length;

        if (visible >= group.length) {
          placement.querySelector(".or-native-x-more-shell")?.remove();
        }
      };

      if (group.length > INITIAL_PER_SECTION) {
        ensureShowMore(placement, () => append(LOAD_MORE_STEP));
      }

      append(INITIAL_PER_SECTION);
    });
  };

  (async () => {
    let posts = [];
    try {
      posts = await fetchLivePosts();
    } catch (error) {
      console.warn("Live Twitter feed unavailable; using cached feed.", error);
      posts = await fetchCachedPosts();
    }

    distribute(posts);
  })();
})();
