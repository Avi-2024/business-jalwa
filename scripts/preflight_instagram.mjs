import fs from "node:fs/promises";
import { selectDuePost } from "./social_queue.mjs";

const POSTS_FILE = process.env.POSTS_FILE || "posts.json";
const posts = JSON.parse(await fs.readFile(POSTS_FILE, "utf8"));

if (!Array.isArray(posts)) {
  throw new Error("posts.json must contain a JSON array.");
}

const due = selectDuePost(posts);

if (!due) {
  console.log("No due Instagram post.");
  process.exit(0);
}

if (!due.id || typeof due.id !== "string") {
  throw new Error("Due post is missing a string id.");
}

if (!Array.isArray(due.image_urls) || due.image_urls.length < 1 || due.image_urls.length > 10) {
  throw new Error("Due post must contain between 1 and 10 image_urls.");
}

const caption = due.caption || "";
if (typeof caption !== "string") {
  throw new Error("Due post caption must be a string.");
}
if ([...caption].length > 2200) {
  throw new Error(`Instagram caption exceeds 2200 characters (${[...caption].length}).`);
}

for (let index = 0; index < due.image_urls.length; index += 1) {
  const imageUrl = due.image_urls[index];
  let parsed;
  try {
    parsed = new URL(imageUrl);
  } catch {
    throw new Error(`Image ${index + 1} has an invalid URL.`);
  }

  if (parsed.protocol !== "https:") {
    throw new Error(`Image ${index + 1} must use HTTPS.`);
  }
  if (!/\.jpe?g$/i.test(parsed.pathname)) {
    throw new Error(`Image ${index + 1} must be a JPEG URL (.jpg or .jpeg).`);
  }

  const response = await fetch(imageUrl, { redirect: "follow" });
  if (!response.ok) {
    throw new Error(`Image ${index + 1} is not publicly reachable (HTTP ${response.status}).`);
  }

  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.startsWith("image/jpeg")) {
    throw new Error(`Image ${index + 1} returned ${contentType || "an unknown content type"}; expected image/jpeg.`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.length < 10_000 || bytes[0] !== 0xff || bytes[1] !== 0xd8 || bytes.at(-2) !== 0xff || bytes.at(-1) !== 0xd9) {
    throw new Error(`Image ${index + 1} is not a valid complete JPEG file.`);
  }

  console.log(`Media ${index + 1}/${due.image_urls.length} OK (${bytes.length} bytes).`);
}


console.log(`Preflight OK for ${due.id}: ${due.image_urls.length} image(s), caption ${[...caption].length} chars.`);
