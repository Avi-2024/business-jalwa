// Only explicitly approved carousels with repository-hosted assets are eligible.
export function isApprovedPost(post) {
  return Boolean(
    post &&
    post.manual_approved === true &&
    Array.isArray(post.image_urls) &&
    post.image_urls.length > 0 &&
    post.image_urls.every((url) =>
      typeof url === "string" && (/\/assets\/(?:content-bank|daily|approved)\/[^?#]+\.jpe?g(?:[?#]|$)/i.test(url))
    )
  );
}

export function isPending(post) {
  return Boolean(
    post &&
    isApprovedPost(post) &&
    !post.published_at &&
    !post.skipped_at &&
    post.publish_at &&
    Number.isFinite(new Date(post.publish_at).getTime())
  );
}

export function getDuePosts(posts, now = new Date()) {
  if (!Array.isArray(posts)) return [];

  const nowMs = now instanceof Date ? now.getTime() : new Date(now).getTime();
  if (!Number.isFinite(nowMs)) throw new Error("Invalid queue evaluation time.");

  return posts
    .map((post, index) => ({
      post,
      index,
      publishMs: post?.publish_at ? new Date(post.publish_at).getTime() : NaN,
    }))
    .filter(({ post, publishMs }) => isPending(post) && publishMs <= nowMs)
    .sort((a, b) => a.publishMs - b.publishMs || a.index - b.index)
    .map(({ post }) => post);
}

export function selectDuePost(posts, now = new Date()) {
  return getDuePosts(posts, now)[0] || null;
}
