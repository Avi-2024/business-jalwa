import fs from "node:fs/promises";
import { selectDuePost } from "./social_queue.mjs";

const IG_USER_ID = process.env.IG_USER_ID;
if (!/^\d+$/.test(IG_USER_ID || "")) throw new Error("Set IG_USER_ID to the Business Jalwa Instagram API account ID.");
const EXPECTED_USERNAME = "business.jalwa";
const ACCESS_TOKEN = (process.env.META_ACCESS_TOKEN || "").trim();
const GRAPH_VERSION = process.env.META_GRAPH_VERSION || "v23.0";
const POSTS_FILE = process.env.POSTS_FILE || "posts.json";
const GRAPH_HOST = "https://graph.instagram.com/";

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

let posts;
let due;
async function saveQueue() {
  await fs.writeFile(POSTS_FILE, JSON.stringify(posts, null, 2) + "\n");
}

async function handleGraphFailure(response, data) {
  const code = Number(data?.error?.code);
  if (due && (response.status === 429 || [4, 17, 32, 613].includes(code))) {
    due.instagram_retry_after = new Date(Date.now() + 6 * 60 * 60 * 1000).toISOString();
    due.instagram_last_error = formatGraphError(response, data);
    await saveQueue();
  }
  throw new Error(formatGraphError(response, data));
}

function formatGraphError(response, data) {
  const error = data?.error || {};
  const details = [
    error.type && `type=${error.type}`,
    error.code != null && `code=${error.code}`,
    error.error_subcode != null && `subcode=${error.error_subcode}`,
  ].filter(Boolean).join(", ");

  return `${error.message || `Instagram Graph API request failed (${response.status})`}${details ? ` (${details})` : ""}`;
}

async function graphPost(path, params = {}) {
  const url = new URL(GRAPH_HOST + GRAPH_VERSION + "/" + path);
  const body = new URLSearchParams({ access_token: ACCESS_TOKEN });

  for (const [key, value] of Object.entries(params)) {
    body.set(key, Array.isArray(value) ? value.join(",") : String(value));
  }

  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = await response.json();

  if (!response.ok || data.error) {
    if (path === `${IG_USER_ID}/media_publish` && due?.instagram_attempt) {
      due.instagram_attempt.publish_failed_at = new Date().toISOString();
      due.instagram_attempt.publish_error = {
        code: data?.error?.code ?? null,
        subcode: data?.error?.error_subcode ?? null,
        message: formatGraphError(response, data),
      };
      await saveQueue();
    }
    await handleGraphFailure(response, data);
  }
  return data;
}

async function graphGet(path, params = {}) {
  const url = new URL(GRAPH_HOST + GRAPH_VERSION + "/" + path);
  url.searchParams.set("access_token", ACCESS_TOKEN);

  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, Array.isArray(value) ? value.join(",") : String(value));
  }

  const response = await fetch(url);
  const data = await response.json();

  if (!response.ok || data.error) await handleGraphFailure(response, data);
  return data;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function markPublished(media) {
  due.published_at = media.timestamp || new Date().toISOString();
  due.instagram_media_id = media.id;
  delete due.instagram_attempt;
  delete due.instagram_retry_after;
  delete due.instagram_last_error;
  await saveQueue();
  console.log(`Published Instagram post ${due.id} as media ${media.id}`);
}

// Recover a publish response lost before its media ID reached the queue.
// Only a unique caption/type/time match can be adopted; never blindly repost.
async function recoverPublishedMedia(attempt) {
  const since = new Date(attempt.publish_requested_at || attempt.started_at).getTime() - 60_000;
  if (!Number.isFinite(since)) throw new Error("Saved Instagram attempt has an invalid timestamp.");
  const knownIds = new Set(posts.filter((post) => post !== due).map((post) => post.instagram_media_id).filter(Boolean));
  let after;
  const matches = [];
  for (let page = 0; page < 5; page++) {
    const result = await graphGet(`${IG_USER_ID}/media`, {
      fields: "id,caption,timestamp,media_type", limit: 100, ...(after ? { after } : {}),
    });
    if (!Array.isArray(result.data)) throw new Error("Instagram media lookup returned no media list.");
    for (const media of result.data) {
      if (!knownIds.has(media.id) && media.caption === (due.caption || "") &&
          new Date(media.timestamp).getTime() >= since &&
          (due.image_urls.length === 1 || media.media_type === "CAROUSEL_ALBUM")) matches.push(media);
    }
    if (!result.paging?.next) {
      if (matches.length > 1) throw new Error("Multiple existing Instagram posts match this attempt; refusing a duplicate.");
      if (matches.length === 1) {
        await markPublished(matches[0]);
        console.log("Recovered an already published Instagram post without uploading again.");
        return true;
      }
      return false;
    }
    after = result.paging?.cursors?.after;
    if (!after) throw new Error("Instagram media lookup cannot safely continue pagination.");
  }
  throw new Error("Instagram media lookup exceeded its recovery limit; refusing an uncertain repost.");
}

async function waitForContainer(containerId, label) {
  const maxChecks = 5;

  for (let check = 1; check <= maxChecks; check += 1) {
    const status = await graphGet(containerId, { fields: "status_code,status" });
    const code = status.status_code;

    if (code === "FINISHED" || code === "PUBLISHED") {
      console.log(`${label} container is ready (${code}).`);
      return code;
    }

    if (code === "ERROR" || code === "EXPIRED") {
      throw new Error(`${label} container failed: ${status.status || code}`);
    }

    if (check === maxChecks) {
      throw new Error(`${label} container was not ready after ${maxChecks} status checks (last status: ${code || "unknown"}).`);
    }

    console.log(`${label} container status: ${code || "processing"}; waiting 60 seconds.`);
    await sleep(60_000);
  }
}

posts = JSON.parse(await fs.readFile(POSTS_FILE, "utf8"));
if (!Array.isArray(posts)) throw new Error("posts.json must contain a JSON array.");
due = selectDuePost(posts);
if (!due) { console.log("No due Instagram post."); process.exit(0); }
if (new Date(due.instagram_retry_after).getTime() > Date.now()) {
  console.log(`Instagram rate-limit cooldown until ${due.instagram_retry_after}; no API requests made.`);
  process.exit(0);
}
const account = await graphGet(IG_USER_ID, { fields: "id,username" });
if (String(account.username || "").toLowerCase() !== EXPECTED_USERNAME.toLowerCase()) {
  throw new Error(`Instagram account mismatch: expected @${EXPECTED_USERNAME}.`);
}
console.log(`Instagram publishing account verified: @${account.username} (${account.id}).`);

if (!Array.isArray(due.image_urls) || due.image_urls.length < 1 || due.image_urls.length > 10) {
  throw new Error("Due post must contain between 1 and 10 image_urls.");
}

// Clear stale verification/publish fields before this fresh publish attempt.
due.instagram_media_id = null;
due.instagram_permalink = null;
due.instagram_username = null;
due.verified_at = null;
due.media_type = null;
due.media_product_type = null;
delete due.verification_error;
delete due.verification_failed_at;

console.log(`Publishing ${due.id} with ${due.image_urls.length} image(s).`);

// Persist each container so a retry does not create another six children.
const signature = JSON.stringify([due.image_urls, due.caption]);
let attempt = due.instagram_attempt;
const agedAttempt = attempt && Date.now() - new Date(attempt.started_at).getTime() > 23 * 60 * 60 * 1000;
if (attempt?.publish_requested_at && (agedAttempt || !attempt.publish_failed_at)) {
  if (await recoverPublishedMedia(attempt)) process.exit(0);
}
if (attempt?.publish_requested_at && attempt.signature !== signature) {
  throw new Error("The queue content changed after a publish request; review the saved attempt before replacing it.");
}
if (attempt?.creation_id && agedAttempt) {
  const saved = await graphGet(attempt.creation_id, { fields: "status_code,status" });
  if (saved.status_code === "PUBLISHED") {
    throw new Error("Saved container is published but its media ID could not be recovered; refusing a duplicate.");
  }
  if (["EXPIRED", "ERROR"].includes(saved.status_code)) {
    console.log(`Saved container is ${saved.status_code}; rebuilding uploads from the approved images.`);
    attempt = null;
  }
}
if (!attempt || attempt.signature !== signature || (agedAttempt && !attempt.creation_id)) {
  attempt = { signature, started_at: new Date().toISOString(), child_ids: [], creation_id: null };
  due.instagram_attempt = attempt;
  await saveQueue();
}
if (!attempt.creation_id) {
  if (due.image_urls.length === 1) {
    const created = await graphPost(`${IG_USER_ID}/media`, { image_url: due.image_urls[0], caption: due.caption || "" });
    attempt.creation_id = created.id;
    await saveQueue();
  } else {
    for (let index = attempt.child_ids.length; index < due.image_urls.length; index++) {
      const child = await graphPost(`${IG_USER_ID}/media`, { image_url: due.image_urls[index], is_carousel_item: "true" });
      attempt.child_ids.push(child.id);
      await saveQueue();
    }
    await Promise.all(attempt.child_ids.map((id, index) => waitForContainer(id, `Carousel item ${index + 1}`)));
    const created = await graphPost(`${IG_USER_ID}/media`, { media_type: "CAROUSEL", children: attempt.child_ids, caption: due.caption || "" });
    attempt.creation_id = created.id;
    await saveQueue();
  }
}
const status = await waitForContainer(attempt.creation_id, "Post");
if (status === "PUBLISHED") {
  if (await recoverPublishedMedia(attempt)) process.exit(0);
  throw new Error("Saved container is published but its media ID could not be recovered; refusing a duplicate.");
}
const creation = { id: attempt.creation_id };

attempt.publish_requested_at = new Date().toISOString();
delete attempt.publish_failed_at;
delete attempt.publish_error;
await saveQueue();
const published = await graphPost(`${IG_USER_ID}/media_publish`, {
  creation_id: creation.id,
});

if (!published.id) throw new Error("Instagram media_publish did not return a media id.");

await markPublished(published);
