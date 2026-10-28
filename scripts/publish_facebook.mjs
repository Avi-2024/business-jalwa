import fs from 'node:fs/promises';
import { isApprovedPost } from './social_queue.mjs';

const file = process.env.POSTS_FILE || 'posts.json';
const posts = JSON.parse(await fs.readFile(file, 'utf8'));
if (!Array.isArray(posts)) throw new Error('Queue must be an array.');
const post = posts.filter(p => isApprovedPost(p) && !p.skipped_at && p.verified_at && p.instagram_media_id && !p.facebook_post_id)
  .sort((a,b) => new Date(a.publish_at) - new Date(b.publish_at))[0];
if (!post) { console.log('No Instagram-verified post pending Facebook.'); process.exit(0); }
const id = process.env.FACEBOOK_PAGE_ID || '';
const token = (process.env.FACEBOOK_PAGE_ACCESS_TOKEN || '').trim();
if (!/^\d+$/.test(id) || !token) throw new Error('Configure FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN.');
const save = () => fs.writeFile(file, JSON.stringify(posts, null, 2) + '\n');
async function api(path, params, method = 'GET') {
  const url = new URL('https://graph.facebook.com/v23.0/' + path);
  const options = {method, headers: {Authorization: 'Bearer ' + token}, signal: AbortSignal.timeout(60000)};
  if (method === 'GET') url.search = new URLSearchParams(params);
  else options.body = new URLSearchParams(params);
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || data.error) throw new Error('Facebook API failed: HTTP ' + response.status + ', code ' + (data.error?.code || 'unknown'));
  return data;
}
const page = await api('me', {fields:'id,name'});
if (String(page.id) !== id || page.name !== 'Business Jalwa') throw new Error(`Page token resolved to ID ${page.id}, name "${page.name}"; expected ID ${id}, name "Business Jalwa".`);
// A request with no saved response may have succeeded. Never resend automatically.
if (post.facebook_attempt?.publish_requested_at) throw new Error('Uncertain Facebook publish outcome. Reconcile the Page post before retrying; no duplicate sent.');
const signature = JSON.stringify([id, post.image_urls, post.facebook_caption || post.caption]);
if (post.facebook_attempt && post.facebook_attempt.signature !== signature) throw new Error('Facebook content changed during upload. Review saved attempt.');
post.facebook_attempt ||= {signature, photo_ids:[]};
await save();
for (let i = post.facebook_attempt.photo_ids.length; i < post.image_urls.length; i++) {
  const photo = await api(id + '/photos', {url:post.image_urls[i], published:'false'}, 'POST');
  if (!photo.id) throw new Error('Photo upload returned no ID.');
  post.facebook_attempt.photo_ids.push(photo.id);
  await save();
}
const params = {message:post.facebook_caption || post.caption || '', published:'true'};
post.facebook_attempt.photo_ids.forEach((photo, i) => params['attached_media[' + i + ']'] = JSON.stringify({media_fbid:photo}));
post.facebook_attempt.publish_requested_at = new Date().toISOString();
await save();
const result = await api(id + '/feed', params, 'POST');
if (!result.id) throw new Error('Feed request returned no ID; review Page before retry.');
post.facebook_post_id = result.id;
post.facebook_page_id = id;
post.facebook_posted_at = new Date().toISOString();
delete post.facebook_attempt;
await save();
console.log('Published Facebook post ' + result.id);
