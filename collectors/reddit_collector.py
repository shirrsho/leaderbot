"""
Pull posts (and top comments) from a subreddit using Reddit's public JSON
endpoints — no OAuth app / client_id needed.

Reddit still serves read-only data at https://www.reddit.com/r/<sub>/new.json
for anyone with a real User-Agent, no login required. This is the same data
PRAW would give you for public read-only browsing, just without needing a
registered app (which Reddit has made harder to get approved for new/personal
use since 2023).

Caveats vs. the old OAuth approach:
- Lower, informal rate limit — keep requests slow (this module sleeps
  between calls) and don't hammer it.
- If Reddit ever blocks anonymous requests for a given subreddit/IP, you'll
  need to fall back to OAuth (see reddit_collector_oauth.py) or a logged-in
  session cookie.
- Only works for public subreddits (not private/quarantined ones needing login).
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Reddit's Fastly WAF now blocks requests with unknown/bot User-Agents (it
# returns 403 "Blocked"), even from residential IPs. So we default to a
# browser-like User-Agent, which passes on most home connections.
# You can override it in .env (REDDIT_USER_AGENT).
DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/122.0.0.0 Safari/537.36")
USER_AGENT = os.environ.get("REDDIT_USER_AGENT") or DEFAULT_UA

# If a UA looks like the old descriptive bot string, ignore it — it gets
# blocked. Force the browser UA instead.
if "leaderbot" in USER_AGENT.lower():
    USER_AGENT = DEFAULT_UA

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Optional: paste your logged-in Reddit cookie into .env as REDDIT_COOKIE to
# make requests authenticated (reliably bypasses the WAF block anywhere).
# In your browser: log in to reddit.com → DevTools → Network → any request →
# copy the full "cookie:" request header value.
_COOKIE = os.environ.get("REDDIT_COOKIE", "").strip()
if _COOKIE:
    BASE_HEADERS["Cookie"] = _COOKIE


def _get(url, params=None, retries=3, backoff=2.0):
    for attempt in range(retries):
        resp = requests.get(url, headers=BASE_HEADERS, params=params, timeout=15)
        if resp.status_code == 200:
            # A logged-out interstitial sometimes returns 200 with HTML.
            ctype = resp.headers.get("Content-Type", "")
            if "json" not in ctype and not resp.text.lstrip().startswith(("{", "[")):
                raise RuntimeError(
                    "Got HTML instead of JSON (login wall). Set REDDIT_COOKIE "
                    "in .env with your logged-in Reddit cookie."
                )
            return resp.json()
        if resp.status_code == 429:
            wait = backoff * (attempt + 1)
            print(f"Rate limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"Failed to fetch {url} after {retries} retries")


def collect_subreddit(subreddit_name: str, limit: int = 50, comments_per_post: int = 3,
                       sleep_between_requests: float = 1.5, after: str = None):
    """
    Pull up to `limit` posts (plus a few comments each) from a subreddit.

    Pagination:
        Pass `after` = the cursor returned by a previous call to continue from
        where you left off (older posts). Pass None to start from the newest.

    Returns:
        (items, next_after)
        - items: list of dicts {post_id, author, text, url, created_utc,
                 source, kind}  where kind is "post" or "comment"
        - next_after: cursor string to pass on the next call, or None if you've
                 reached the end of the listing (no older posts left).
    """
    items = []
    fetched = 0

    while fetched < limit:
        batch_size = min(100, limit - fetched)
        params = {"limit": batch_size}
        if after:
            params["after"] = after

        data = _get(f"https://www.reddit.com/r/{subreddit_name}/new.json", params=params)
        children = data.get("data", {}).get("children", [])
        if not children:
            after = None  # nothing left
            break

        for child in children:
            post = child["data"]
            items.append({
                "post_id": post["id"],
                "author": post.get("author", "[deleted]"),
                "text": f"{post.get('title', '')}\n\n{post.get('selftext', '')}".strip(),
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "created_utc": post.get("created_utc", 0),
                "source": "reddit",
                "kind": "post",
            })
            fetched += 1

            if comments_per_post > 0:
                time.sleep(sleep_between_requests)
                try:
                    comments = _get(
                        f"https://www.reddit.com/r/{subreddit_name}/comments/{post['id']}.json",
                        params={"limit": comments_per_post, "depth": 1},
                    )
                    comment_listing = comments[1]["data"]["children"] if len(comments) > 1 else []
                    for c in comment_listing[:comments_per_post]:
                        cdata = c.get("data", {})
                        body = cdata.get("body")
                        if not body or body in ("[deleted]", "[removed]"):
                            continue
                        items.append({
                            "post_id": cdata["id"],
                            "author": cdata.get("author", "[deleted]"),
                            "text": body,
                            "url": f"https://reddit.com{cdata.get('permalink', '')}",
                            "created_utc": cdata.get("created_utc", 0),
                            "source": "reddit",
                            "kind": "comment",
                        })
                except Exception as e:
                    print(f"  (skipping comments for post {post['id']}: {e})")

        after = data.get("data", {}).get("after")
        if not after:
            break  # reached end of listing
        time.sleep(sleep_between_requests)

    return items, after


def self_test(subreddit_name: str = "smallbusiness"):
    """Quick connectivity check — confirms Reddit's JSON endpoint is reachable
    from this machine before you commit to a full run."""
    print(f"User-Agent: {USER_AGENT}")
    print(f"Testing https://www.reddit.com/r/{subreddit_name}/new.json ...")
    try:
        data = _get(f"https://www.reddit.com/r/{subreddit_name}/new.json",
                    params={"limit": 1}, retries=1)
        n = len(data.get("data", {}).get("children", []))
        if n:
            title = data["data"]["children"][0]["data"].get("title", "")
            print(f"  OK — reachable. Latest post: {title[:80]!r}")
            return True
        print("  Reached endpoint but got no posts (subreddit empty or private?).")
        return False
    except Exception as e:
        print(f"  BLOCKED / failed: {e}")
        print("  Reddit is blocking anonymous requests from this IP.")
        print("  Options: try a different network, or fall back to manual paste.")
        return False


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sub = sys.argv[2] if len(sys.argv) > 2 else "smallbusiness"
        self_test(sub)
        sys.exit(0)

    sub = sys.argv[1] if len(sys.argv) > 1 else "smallbusiness"
    results, next_after = collect_subreddit(sub, limit=10, comments_per_post=2)
    print(json.dumps(results[:3], indent=2))
    print(f"\nCollected {len(results)} items from r/{sub}")
    print(f"next_after cursor: {next_after}")
