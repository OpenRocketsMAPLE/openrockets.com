import fs from "node:fs/promises";

const HANDLE = "maplelicense";
const MAX_POSTS = 100;
const WIDGET_ID = "739491f1-b20f-438a-837a-73fb487ee5f2";
const PAGE_URL = "https://openrockets.com/";
const CORE_URL = "https://core.service.elfsight.com";
const DATA_URL = "https://widget-data.service.elfsight.com";
const FX_URL = "https://api.fxtwitter.com";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const sameHandle = (value) => String(value || "").replace(/^@/, "").toLowerCase() === HANDLE;

async function fetchWithRetry(url, options = {}, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const response = await fetch(url, {
        ...options,
        signal: AbortSignal.timeout(20000),
        headers: {
          Accept: "application/json",
          "User-Agent": "OpenRockets-X-Feed/1.0 (+https://openrockets.com)",
          ...(options.headers || {})
        }
      });
      if (response.ok || response.status === 204) return response;
      lastError = new Error(`HTTP ${response.status} from ${url}`);
    } catch (error) {
      lastError = error;
    }
    if (attempt < attempts) await sleep(attempt * 1500);
  }
  throw lastError;
}

function rawMediaItems(media = {}) {
  const source = Array.isArray(media?.all)
    ? media.all
    : [
        ...(Array.isArray(media?.photos) ? media.photos : []),
        ...(Array.isArray(media?.videos) ? media.videos : [])
      ];

  const seen = new Set();
  return source.filter((item) => {
    const key = String(item?.id || item?.url || item?.thumbnail_url || "");
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeMedia(media = {}) {
  return rawMediaItems(media).map((item) => {
    const isVideo = item?.type === "video" || item?.type === "gif";
    const displayUrl = isVideo
      ? (item?.thumbnail_url || item?.url || null)
      : (item?.url || item?.thumbnail_url || null);

    return {
      type: isVideo ? "video" : "image",
      thumbnail: item?.thumbnail_url ? { url: item.thumbnail_url } : null,
      standard: displayUrl
        ? { url: displayUrl, width: item?.width ?? null, height: item?.height ?? null }
        : null,
      original: item?.url
        ? { url: item.url, width: item?.width ?? null, height: item?.height ?? null }
        : null,
      id: item?.id ? String(item.id) : null
    };
  }).filter((item) => item.standard?.url || item.original?.url || item.thumbnail?.url);
}

function normalizeAuthor(author = {}) {
  return {
    username: author?.screen_name || HANDLE,
    url: author?.url || null,
    profilePictureUrl: author?.avatar_url || null,
    isVerifiedProfile: Boolean(author?.verification?.verified),
    name: author?.name || author?.screen_name || HANDLE,
    biography: author?.description || "",
    postsCount: author?.statuses ?? null,
    followersCount: author?.followers ?? null,
    followingCount: author?.following ?? null
  };
}

function normalizeStatus(status, depth = 0) {
  if (!status || status.type !== "status" || !status.id) return null;

  const reply = status?.replying_to || null;
  const quoted = depth < 2 ? normalizeStatus(status?.quote, depth + 1) : null;
  const type = status?.reposted_by
    ? "repost"
    : reply
      ? "reply"
      : quoted
        ? "quote"
        : "post";

  return {
    vendorId: String(status.id),
    type,
    link: status?.url || `https://x.com/${status?.author?.screen_name || HANDLE}/status/${status.id}`,
    publishedAt: status?.created_timestamp
      ? new Date(Number(status.created_timestamp) * 1000).toISOString()
      : status?.created_at || null,
    author: normalizeAuthor(status?.author),
    media: normalizeMedia(status?.media),
    comments: [],
    caption: status?.text || "",
    commentsCount: status?.replies ?? null,
    likesCount: status?.likes ?? 0,
    shareCount: status?.reposts ?? null,
    extra: {
      platform: "twitter",
      replyCount: status?.replies ?? 0,
      repostCount: status?.reposts ?? 0,
      viewCount: status?.views ?? null,
      repost: status?.reposted_by || null,
      inReplyTo: reply
        ? {
            vendorId: reply?.status ? String(reply.status) : null,
            type: "post",
            link: reply?.url || (reply?.status
              ? `https://x.com/${reply?.screen_name || HANDLE}/status/${reply.status}`
              : null),
            author: reply?.screen_name
              ? { username: reply.screen_name, name: reply.display_name || reply.screen_name }
              : null
          }
        : null,
      quoted
    },
    isPinned: null,
    isPinnedManually: false
  };
}

function isAllowedTopLevelFx(status) {
  if (!status || status.type !== "status" || !status.id) return false;
  if (!sameHandle(status?.author?.screen_name)) return false;
  if (status?.replying_to) return false;
  if (status?.reposted_by) return false;
  return true;
}

function isAllowedElfsight(post) {
  const author = post?.author?.username;
  if (author && !sameHandle(author)) return false;
  if (post?.type === "reply" || post?.type === "repost") return false;
  if (post?.extra?.inReplyTo || post?.extra?.repost) return false;
  return true;
}

function normalizeElfsightPost(post) {
  return {
    ...post,
    type: post?.extra?.quoted ? "quote" : "post"
  };
}

async function fetchFxTwitterPosts() {
  const collected = [];
  const seen = new Set();
  let cursor = null;

  for (let page = 0; page < 10 && collected.length < MAX_POSTS; page += 1) {
    const url = new URL(`/2/profile/${HANDLE}/statuses`, FX_URL);
    url.searchParams.set("count", "100");
    url.searchParams.set("with_replies", "0");
    if (cursor) url.searchParams.set("cursor", cursor);

    const response = await fetchWithRetry(url);
    if (response.status === 204) break;

    const payload = await response.json();
    if (payload?.code !== 200 || !Array.isArray(payload?.results)) {
      throw new Error(`FxTwitter returned invalid timeline data (code ${payload?.code ?? "unknown"})`);
    }

    for (const raw of payload.results) {
      if (!isAllowedTopLevelFx(raw)) continue;
      const post = normalizeStatus(raw);
      if (!post || seen.has(post.vendorId)) continue;
      seen.add(post.vendorId);
      collected.push(post);
      if (collected.length >= MAX_POSTS) break;
    }

    const next = payload?.cursor?.bottom;
    if (!next || next === cursor || !payload.results.length) break;
    cursor = next;
  }

  if (!collected.length) {
    throw new Error("FxTwitter returned no original or quote posts for @maplelicense");
  }

  return collected
    .sort((a, b) => new Date(b.publishedAt || 0) - new Date(a.publishedAt || 0))
    .slice(0, MAX_POSTS);
}

async function fetchElfsightPosts() {
  const bootUrl = new URL("/p/boot/", CORE_URL);
  bootUrl.searchParams.set("w", WIDGET_ID);
  bootUrl.searchParams.set("page", PAGE_URL);

  const bootResponse = await fetchWithRetry(bootUrl);
  const boot = await bootResponse.json();
  const widget = boot?.data?.widgets?.[WIDGET_ID]?.data;

  if (!widget?.public_widget_token) {
    throw new Error("Elfsight did not return a public widget token");
  }

  const account = widget?.settings?.account;
  if (!account?.pid) {
    throw new Error("Elfsight did not return the MAPLE account source");
  }

  const filters = [
    { type: "exclude", post_type: "reply" },
    { type: "exclude", post_type: "repost" }
  ];

  const postsUrl = new URL("/api/posts", DATA_URL);
  postsUrl.searchParams.append(
    "sources[]",
    JSON.stringify({ pid: account.pid, filters })
  );
  postsUrl.searchParams.set("sort", "date");
  postsUrl.searchParams.set("limit", String(MAX_POSTS));
  postsUrl.searchParams.set("offset", "0");

  const postsResponse = await fetchWithRetry(postsUrl, {
    headers: { "x-widget-token": widget.public_widget_token }
  });

  const payload = await postsResponse.json();
  if (payload?.code !== 200 || !Array.isArray(payload?.payload)) {
    throw new Error("Elfsight X feed returned invalid JSON");
  }

  const seen = new Set();
  return payload.payload
    .filter(isAllowedElfsight)
    .map(normalizeElfsightPost)
    .filter((post) => {
      const id = String(post?.vendorId || post?.id || "");
      if (!id || seen.has(id)) return false;
      seen.add(id);
      return true;
    })
    .slice(0, MAX_POSTS);
}

let posts;
let provider;

try {
  posts = await fetchFxTwitterPosts();
  provider = "fxtwitter";
  console.log(`Fetched ${posts.length} original/quote posts from FxTwitter.`);
} catch (fxError) {
  console.warn("FxTwitter refresh failed; trying Elfsight fallback:", fxError?.message || fxError);
  posts = await fetchElfsightPosts();
  provider = "elfsight";
  console.log(`Fetched ${posts.length} original/quote posts from Elfsight fallback.`);
}

const output = {
  fetchedAt: new Date().toISOString(),
  source: "@maplelicense",
  provider,
  filter: "original-and-quote-posts-only",
  widgetId: WIDGET_ID,
  count: posts.length,
  posts
};

await fs.mkdir("data", { recursive: true });
await fs.writeFile("data/x-feed.json", JSON.stringify(output, null, 2) + "\n");
console.log(`Saved ${posts.length} original/quote X posts to data/x-feed.json via ${provider}`);
