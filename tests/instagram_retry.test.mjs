import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const publisher = fileURLToPath(new URL("../scripts/publish_instagram.mjs", import.meta.url));
const verifier = fileURLToPath(new URL("../scripts/verify_instagram_publish.mjs", import.meta.url));
const mock = `
import fs from "node:fs";
const calls = [];
const mode = process.env.MOCK_MODE;
const post = JSON.parse(fs.readFileSync(process.env.POSTS_FILE))[0];
globalThis.fetch = async (input, options = {}) => {
  const url = new URL(input);
  const endpoint = url.pathname.split("/").pop();
  const method = options.method || "GET";
  calls.push({endpoint, method});
  fs.writeFileSync(process.env.CALLS_FILE, JSON.stringify(calls));
  let data;
  let status = 200;
  if (endpoint === "17841424749134562") data = {id: endpoint, username: "business.jalwa"};
  else if (method === "GET" && endpoint === "media") {
    const item = {id: "existing-media", caption: post.caption, timestamp: new Date().toISOString(), media_type: "CAROUSEL_ALBUM"};
    data = {data: mode === "recover" ? [item] : mode === "ambiguous" ? [item, {...item, id: "second-media"}] : []};
  } else if (method === "GET" && endpoint === "existing-media") {
    data = {id: "existing-media", username: "business.jalwa", permalink: "https://www.instagram.com/p/existing/", timestamp: new Date().toISOString(), media_type: "CAROUSEL_ALBUM"};
  } else if (method === "GET") {
    data = {status_code: endpoint === "old-parent" ? (mode === "expired" ? "EXPIRED" : mode === "published-missing" ? "PUBLISHED" : "FINISHED") : "FINISHED"};
  } else if (endpoint === "media_publish") {
    if (mode === "rate-limit") {status = 429; data = {error: {message: "Application request limit reached", code: 4, error_subcode: 2207051}};}
    else data = {id: "new-media"};
  } else if (endpoint === "media") data = {id: "new-container-" + calls.length};
  else throw new Error("Unexpected mock endpoint");
  return {ok: status === 200, status, json: async () => data};
};
`;

async function run(mode, changes = {}, script = publisher) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "instagram-retry-"));
  try {
    const post = {
      id: "approved-test", manual_approved: true, ai_visual_used: true,
      publish_at: "2026-01-01T09:00:00+05:30", caption: "A unique approved caption",
      image_urls: Array.from({length: 6}, (_, i) => `https://example.com/assets/approved/day/slide-${i + 1}.jpg`),
    };
    post.instagram_attempt = {
      signature: JSON.stringify([post.image_urls, post.caption]),
      started_at: "2026-01-02T01:00:00Z", publish_requested_at: "2026-01-02T01:01:00Z",
      child_ids: ["1", "2", "3", "4", "5", "6"], creation_id: "old-parent",
    };
    Object.assign(post, changes);
    const postsFile = path.join(dir, "posts.json");
    const callsFile = path.join(dir, "calls.json");
    const mockFile = path.join(dir, "mock.mjs");
    await fs.writeFile(postsFile, JSON.stringify([post]));
    await fs.writeFile(mockFile, mock);
    const result = spawnSync(process.execPath, ["--import", mockFile, script], {
      encoding: "utf8", env: {...process.env, META_ACCESS_TOKEN: "test-token", IG_USER_ID: "17841424749134562", POSTS_FILE: postsFile, CALLS_FILE: callsFile, MOCK_MODE: mode},
    });
    const saved = JSON.parse(await fs.readFile(postsFile, "utf8"))[0];
    const calls = JSON.parse(await fs.readFile(callsFile, "utf8").catch(() => "[]"));
    return {result, saved, calls};
  } finally { await fs.rm(dir, {recursive: true, force: true}); }
}

test("expired rejected attempt rebuilds approved uploads and publishes", async () => {
  const {result, saved, calls} = await run("expired", {instagram_last_error: "Application request limit reached (code=4, subcode=2207051)"});
  assert.equal(result.status, 0, result.stderr);
  assert.equal(saved.instagram_media_id, "new-media");
  assert.equal(saved.instagram_attempt, undefined);
  assert.equal(calls.filter(c => c.method === "POST" && c.endpoint === "media").length, 7);
  assert.equal(calls.filter(c => c.endpoint === "media_publish").length, 1);
});

test("finished old parent is reused without recreating images", async () => {
  const {result, saved, calls} = await run("ready");
  assert.equal(result.status, 0, result.stderr);
  assert.equal(saved.instagram_media_id, "new-media");
  assert.equal(calls.filter(c => c.method === "POST" && c.endpoint === "media").length, 0);
});

test("lost successful response recovers existing media without reposting", async () => {
  const {result, saved, calls} = await run("recover");
  assert.equal(result.status, 0, result.stderr);
  assert.equal(saved.instagram_media_id, "existing-media");
  assert.equal(calls.some(c => c.method === "POST"), false);
});

test("published container with no unique media match never reposts", async () => {
  const {result, saved, calls} = await run("published-missing");
  assert.notEqual(result.status, 0);
  assert.equal(saved.published_at, undefined);
  assert.equal(calls.some(c => c.method === "POST"), false);
});

test("ambiguous existing media never reposts", async () => {
  const {result, calls} = await run("ambiguous");
  assert.notEqual(result.status, 0);
  assert.equal(calls.some(c => c.method === "POST"), false);
});

test("API rejection records structured failure and a cooldown", async () => {
  const {result, saved} = await run("rate-limit");
  assert.notEqual(result.status, 0);
  assert.equal(saved.instagram_attempt.publish_error.code, 4);
  assert.ok(saved.instagram_attempt.publish_failed_at);
  assert.ok(new Date(saved.instagram_retry_after).getTime() > Date.now());
  assert.equal(saved.published_at, undefined);
});

test("cooldown performs no API requests", async () => {
  const {result, calls} = await run("ready", {instagram_retry_after: new Date(Date.now() + 60_000).toISOString()});
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(calls, []);
});

test("verifier recovers and verifies media after a failed publish response during cooldown", async () => {
  const {result, saved, calls} = await run("recover", {instagram_retry_after: new Date(Date.now() + 60_000).toISOString()}, verifier);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(saved.instagram_media_id, "existing-media");
  assert.ok(saved.verified_at);
  assert.equal(saved.instagram_permalink, "https://www.instagram.com/p/existing/");
  assert.equal(saved.instagram_retry_after, undefined);
  assert.equal(calls.some(c => c.method === "POST"), false);
});

test("verifier keeps a truly rejected post unpublished", async () => {
  const {result, saved, calls} = await run("ready", {}, verifier);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(saved.published_at, undefined);
  assert.ok(saved.instagram_attempt);
  assert.equal(calls.some(c => c.method === "POST"), false);
});
