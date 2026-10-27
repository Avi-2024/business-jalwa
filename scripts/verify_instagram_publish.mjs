import fs from "node:fs/promises";

const IG_USER_ID = process.env.IG_USER_ID;
if (!/^\d+$/.test(IG_USER_ID || "")) throw new Error("Set IG_USER_ID to the Business Jalwa Instagram API account ID.");
const EXPECTED_USERNAME = "business.jalwa";
const ACCESS_TOKEN = (process.env.META_ACCESS_TOKEN || "").trim();
const GRAPH_VERSION = process.env.META_GRAPH_VERSION || "v23.0";
const GRAPH_HOST = "https://graph.instagram.com/";
const POSTS_FILE = process.env.POSTS_FILE || "posts.json";

if (!ACCESS_TOKEN) throw new Error("Missing META_ACCESS_TOKEN repository secret.");
if (/^Bearer\s+/i.test(ACCESS_TOKEN)) {
  throw new Error("META_ACCESS_TOKEN must contain only the raw Instagram access token, without a Bearer prefix.");
}
if (/\s/.test(ACCESS_TOKEN)) {
  throw new Error("META_ACCESS_TOKEN contains whitespace. Save only the raw Instagram access token in the GitHub secret.");
}
if (/^[\"'`]|[\"'`]$/.test(ACCESS_TOKEN)) {
  throw new Error("META_ACCESS_TOKEN appears to be quoted. Save only the raw Instagram access token in the GitHub secret.");
}

function graphError(response, data) {
  const error = data?.error || {};
  const details = [
    error.type && `type=${error.type}`,
    error.code != null && `code=${error.code}`,
    error.error_subcode != null && `subcode=${error.error_subcode}`,
  ].filter(Boolean).join(", ");

  return `${error.message || `Instagram Graph API request failed (${response.status})`}${details ? ` (${details})` : ""}`;
}

async function graphGet(path, params = {}) {
  const url = new URL(`${GRAPH_HOST}${GRAPH_VERSION}/${path}`);
  url.searchParams.set("access_token", ACCESS_TOKEN);

  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, Array.isArray(value) ? value.join(",") : String(value));
  }

  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok || data.error) throw new Error(graphError(response, data));
  return data;
}

const posts = JSON.parse(await fs.readFile(POSTS_FILE, "utf8"));
if (!Array.isArray(posts)) throw new Error("posts.json must contain a JSON array.");

let pending = posts
  .filter((post) => post.published_at && post.instagram_media_id && !post.verified_at)
  .sort((a, b) => new Date(b.published_at) - new Date(a.published_at))[0];

const recoverable = posts
  .filter(post => !post.published_at && post.instagram_attempt?.publish_requested_at && post.instagram_attempt.signature === JSON.stringify([post.image_urls, post.caption]))
  .sort((a, b) => new Date(a.publish_at) - new Date(b.publish_at))[0];

if (!pending && !recoverable) {
  console.log("No Instagram post pending verification.");
  process.exit(0);
}

const account = await graphGet(IG_USER_ID, { fields: "id,username" });
const actualUsername = String(account.username || "").toLowerCase();

if (!actualUsername) throw new Error(`Instagram account ${IG_USER_ID} did not return a username.`);
if (actualUsername !== EXPECTED_USERNAME.toLowerCase()) {
  throw new Error(`Safety stop: Instagram ID ${IG_USER_ID} resolves to @${account.username}, expected @${EXPECTED_USERNAME}.`);
}

console.log(`Authenticated Instagram account: @${account.username} (${account.id})`);

if (!pending && recoverable) {
  // media_publish can return an error after Meta has actually published the post.
  // This is a read-only check: never retry the write to discover its outcome.
  const recent = await graphGet(`${IG_USER_ID}/media`, { fields: "id,caption,timestamp,media_type", limit: 100 });
  if (!Array.isArray(recent.data)) throw new Error("Instagram recovery lookup returned no media list.");
  const since = new Date(recoverable.instagram_attempt.publish_requested_at).getTime() - 60_000;
  if (!Number.isFinite(since)) throw new Error("Instagram recovery attempt has an invalid timestamp.");
  const knownIds = new Set(posts.filter(post => post !== recoverable).map(post => post.instagram_media_id).filter(Boolean));
  const matches = recent.data.filter(media => !knownIds.has(media.id) &&
    media.caption === (recoverable.caption || "") && new Date(media.timestamp).getTime() >= since &&
    (recoverable.image_urls.length === 1 || media.media_type === "CAROUSEL_ALBUM"));
  if (matches.length > 1) throw new Error("Multiple Instagram posts match the failed request; refusing ambiguous recovery.");
  if (!matches.length) {
    console.log(`No published Instagram media found for attempt ${recoverable.id}; queue remains unpublished.`);
    process.exit(0);
  }
  const matched = matches[0];
  recoverable.published_at = matched.timestamp;
  recoverable.instagram_media_id = matched.id;
  delete recoverable.instagram_attempt;
  delete recoverable.instagram_retry_after;
  delete recoverable.instagram_last_error;
  await fs.writeFile(POSTS_FILE, JSON.stringify(posts, null, 2) + "\n");
  pending = recoverable;
  console.log(`Recovered existing Instagram media ${matched.id} after a failed publish response; no new upload.`);
}

console.log(`Verifying Instagram media ${pending.instagram_media_id} for post ${pending.id}.`);

const media = await graphGet(pending.instagram_media_id, {
  fields: "id,media_type,media_product_type,permalink,timestamp,username",
});

if (account.username && media.username && account.username !== media.username) {
  throw new Error(`Published media belongs to @${media.username}, expected @${account.username}.`);
}

if (!media.permalink) throw new Error("Published media exists but Meta did not return a permalink.");

pending.instagram_permalink = media.permalink;
pending.instagram_username = media.username || account.username || null;
pending.verified_at = new Date().toISOString();
pending.media_type = media.media_type || null;
pending.media_product_type = media.media_product_type || null;
delete pending.verification_error;
delete pending.verification_failed_at;

await fs.writeFile(POSTS_FILE, JSON.stringify(posts, null, 2) + "\n");
console.log(`Verified Instagram media ${media.id}.`);
console.log(`Published username: @${pending.instagram_username || "unknown"}`);
console.log(`Instagram permalink: ${media.permalink}`);
