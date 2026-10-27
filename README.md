# Business Jalwa
Instagram publishing foundation for @business.jalwa, adapted from Avi-2024/buildkarbro.
 
## Setup
Repository Settings → Secrets and variables → Actions:
- Secret META_ACCESS_TOKEN: raw Instagram Login access token authorized for business.jalwa.
- Variable IG_USER_ID: numeric Instagram API account ID for that account (not Facebook Page ID).
- Variable PUBLISH_ENABLED: set to true only after credentials and first carousel are ready.

Never put tokens in posts, source files, screenshots or chat. Old account credentials are not copied.
Run the workflow manually with publishing disabled to validate configuration without publishing.
The account check rejects any username other than business.jalwa.

## Content
content/launch-plan.json defines the first ten educational topics followed by company stories.
posts.json is intentionally empty. Images and completed captions have not been generated.
Add entries with unique id, publish_at (ISO timestamp including timezone), caption, image_urls (1–10 public HTTPS JPEGs under /assets/approved/), manual_approved: true.
Only completed, approved posts enter the live queue. The scheduler checks at 09:00 IST; GitHub may delay execution.
No automatic research or content generation is configured. Facebook publisher is implemented but remains disabled until Page authorization is configured.

## Reliability
Single workflow writer; saves attempts and publish results even after a failure; reuses containers and checks for existing media before uncertain retries.
Run npm test for mocked recovery checks. Live API authorization and actual publishing still need testing.

## Facebook publishing
Link the Business Jalwa Page to @business.jalwa in Meta. Set FACEBOOK_PAGE_ID as an Actions variable and FACEBOOK_PAGE_ACCESS_TOKEN as a secret containing an actual Page token. Enable FACEBOOK_PUBLISH_ENABLED=true only after authorization. The publisher sends the same images as a multi-photo Facebook post after Instagram verification. It records Facebook status independently, resumes saved photo uploads, and stops for manual reconciliation if a feed request has an unknown outcome. Disable any other automatic cross-posting for these queued posts to avoid duplicates. Linking accounts alone does not configure API credentials.
