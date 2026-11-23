import fs from "node:fs/promises";

const WIDGET_ID = "739491f1-b20f-438a-837a-73fb487ee5f2";
const MAX_POSTS = 100;
const PAGE_URL = "https://openrockets.com/";
const CORE_URL = "https://core.service.elfsight.com";
const DATA_URL = "https://widget-data.service.elfsight.com";

const bootUrl = new URL("/p/boot/", CORE_URL);
bootUrl.searchParams.set("w", WIDGET_ID);
bootUrl.searchParams.set("page", PAGE_URL);

const bootResponse = await fetch(bootUrl, {
  headers: { Accept: "application/json" }
});
if (!bootResponse.ok) {
  throw new Error(`Elfsight boot failed with HTTP ${bootResponse.status}`);
}

const boot = await bootResponse.json();
const widget = boot?.data?.widgets?.[WIDGET_ID]?.data;
if (!widget?.public_widget_token) {
  throw new Error("Elfsight did not return a public widget token");
}

const account = widget?.settings?.account;
if (!account?.pid) {
  throw new Error("Elfsight did not return the MAPLE account source");
}

const allowed = Array.isArray(widget?.settings?.filterByTypes)
  ? widget.settings.filterByTypes
  : ["reply", "repost", "common"];

const filters = ["reply", "repost", "common"]
  .filter((type) => !allowed.includes(type))
  .map((post_type) => ({ type: "exclude", post_type }));

const postsUrl = new URL("/api/posts", DATA_URL);
postsUrl.searchParams.append(
  "sources[]",
  JSON.stringify({ pid: account.pid, filters })
);
postsUrl.searchParams.set("sort", "date");
postsUrl.searchParams.set("limit", String(MAX_POSTS));
postsUrl.searchParams.set("offset", "0");

const postsResponse = await fetch(postsUrl, {
  headers: {
    Accept: "application/json",
    "x-widget-token": widget.public_widget_token
  }
});
if (!postsResponse.ok) {
  throw new Error(`Elfsight X feed failed with HTTP ${postsResponse.status}`);
}

const payload = await postsResponse.json();
if (payload?.code !== 200 || !Array.isArray(payload?.payload)) {
  throw new Error("Elfsight X feed returned invalid JSON");
}

const seen = new Set();
const posts = payload.payload
  .filter((post) => {
    const id = String(post?.vendorId || post?.id || "");
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  })
  .slice(0, MAX_POSTS);

const output = {
  fetchedAt: new Date().toISOString(),
  source: "@maplelicense",
  widgetId: WIDGET_ID,
  count: posts.length,
  posts
};

await fs.mkdir("data", { recursive: true });
await fs.writeFile("data/x-feed.json", JSON.stringify(output, null, 2) + "\n");
console.log(`Saved ${posts.length} live X posts to data/x-feed.json`);
