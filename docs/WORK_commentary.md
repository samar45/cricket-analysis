# Commentary pilot

MILESTONE: 2026-11-12 robots.txt checked (2 requests). Pilot stopped before any commentary fetch.
- cricbuzz.com/robots.txt: `User-agent: *` -> `Disallow: /` (only /ads.txt allowed). Googlebot-only rules otherwise. Any path we would use (/api/, /match/, *.json) is disallowed for generic agents.
- espncricinfo.com/robots.txt: HTTP 403 "Access Denied" (Akamai bot block) on the very first request. Stopped per conduct rule.
- No match data fetched, no parser written. Needs Samar's decision (see report).
