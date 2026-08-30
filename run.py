"""
Main entrypoint.

Usage:
    # Reddit:
    python run.py reddit smallbusiness --product "a CRM tool for small teams" --limit 50

    # Manual/pasted text file (e.g. copied from a Facebook group):
    python run.py manual posts.txt facebook --product "a CRM tool for small teams"
"""
import argparse
from datetime import datetime, timezone

from storage.db import init_db, upsert_lead
from extractor import extract_leads


def save_results(results):
    saved = 0
    for r in results:
        upsert_lead({
            "source": r["source"],
            "post_id": r["post_id"],
            "author": r["author"],
            "text": r["text"],
            "post_url": r.get("url", ""),
            "is_lead": int(r["is_lead"]),
            "confidence": r["confidence"],
            "reason": r["reason"],
            "intent": r["intent"],
            "urgency": r["urgency"],
            "contact_hint": "",
            "created_at": datetime.fromtimestamp(
                r.get("created_utc", 0), tz=timezone.utc
            ).isoformat() if r.get("created_utc") else "",
        })
        saved += 1
    return saved


def main():
    parser = argparse.ArgumentParser(description="Collect posts and extract leads via Groq.")
    parser.add_argument("mode", choices=["reddit", "manual"])
    parser.add_argument("target", help="subreddit name, or path to a manual .txt file")
    parser.add_argument("source_label", nargs="?", default="manual",
                         help="(manual mode only) label for source, e.g. facebook")
    parser.add_argument("--product", required=True,
                         help="Description of what you're selling/offering, used to judge leads")
    parser.add_argument("--limit", type=int, default=50, help="(reddit mode) number of posts to pull")

    args = parser.parse_args()
    init_db()

    if args.mode == "reddit":
        from collectors.reddit_collector import collect_subreddit
        items = collect_subreddit(args.target, limit=args.limit)
    else:
        from collectors.manual_collector import parse_text_file
        items = parse_text_file(args.target, args.source_label)

    print(f"Collected {len(items)} items.")
    if not items:
        return

    results = extract_leads(items, product_description=args.product)
    saved = save_results(results)
    leads_found = sum(1 for r in results if r["is_lead"])

    print(f"Processed {len(results)} items, saved {saved} rows, {leads_found} flagged as leads.")
    print("Run `python review.py` to view/export flagged leads.")


if __name__ == "__main__":
    main()
