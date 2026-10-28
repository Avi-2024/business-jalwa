# Business Jalwa
Instagram and Facebook publishing foundation for @business.jalwa.

## Posting schedule
The GitHub Actions workflow checks the queue daily at **09:00 IST** (03:30 UTC) and publishes at most one due, approved post per run. GitHub may delay scheduled runs. Set each post's `publish_at` to its intended 09:00 IST date.

## Asset naming and storage
Keep completed, manually approved carousel slides in `assets/approved/` using this sequence:
- `post-001-slide-01.jpg` through `post-001-slide-05.jpg`
- Next carousel: `post-002-slide-01.jpg`, and continue incrementing the post number.
Keep slides in numerical order. Store draft or not-yet-approved media under `assets/content-bank/`; do not mark a draft as approved in `posts.json`.

The first carousel is queued for **29 October 2026 at 09:00 IST**. Its images and caption are listed in `posts.json`. Queue entries need a unique `id`, ISO `publish_at`, caption, 1–10 public HTTPS JPEG `image_urls`, and `manual_approved: true`.

## Credentials and safety
Repository Settings → Secrets and variables → Actions:
- Secret `META_ACCESS_TOKEN`: raw Instagram access token authorized for @business.jalwa.
- Variable `IG_USER_ID`: numeric Instagram API account ID, not the Facebook Page ID.
- Variable `PUBLISH_ENABLED`: set to `true` to allow scheduled Instagram publishing.
- Secret `FACEBOOK_PAGE_ACCESS_TOKEN` and variable `FACEBOOK_PAGE_ID`: required for Page publishing.
- Variable `FACEBOOK_PUBLISH_ENABLED`: set to `true` to allow Facebook publishing after Instagram verification.

Never put tokens in posts, source files, screenshots, or chat. The account check rejects any username other than @business.jalwa. The queue only publishes explicitly approved entries.

## Reliability
The workflow stores attempts and publish results, reuses containers, and checks for existing media before uncertain retries. Live API authorization and actual publishing still need monitoring after the first scheduled run.
