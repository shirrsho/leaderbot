"""
Generic ingestion for sources with no API access (e.g. Facebook Groups).

You manually copy/paste post text (one post per block, separated by '---')
into a .txt file, or build a list of dicts yourself. This keeps Facebook
scraping out of automation entirely (against their ToS) while reusing the
same downstream extraction pipeline as Reddit.

Usage:
    python manual_collector.py posts.txt facebook

File format (posts.txt):
    Author: Jane Doe
    Looking for a good accountant for my small business in Austin, any recs?
    ---
    Author: John Smith
    Just posting my weekend photos, nothing to see here.
    ---
"""
import sys
import time


def parse_text(raw: str, source: str = "manual"):
    """Parse a raw string of '---'-separated post blocks into items."""
    blocks = [b.strip() for b in raw.split("---") if b.strip()]
    items = []
    now = time.time()

    for i, block in enumerate(blocks):
        author = "unknown"
        text = block
        if block.lower().startswith("author:"):
            first_line, _, rest = block.partition("\n")
            author = first_line.split(":", 1)[1].strip()
            text = rest.strip()

        items.append({
            "post_id": f"{source}-{int(now)}-{i}",
            "author": author,
            "text": text,
            "url": "",
            "created_utc": now,
            "source": source,
            "kind": "post",
        })

    return items


def parse_text_file(path: str, source: str = "manual"):
    """Parse a '---'-separated post file into items."""
    with open(path, "r", encoding="utf-8") as f:
        return parse_text(f.read(), source)


if __name__ == "__main__":
    import json

    path = sys.argv[1] if len(sys.argv) > 1 else "posts.txt"
    source = sys.argv[2] if len(sys.argv) > 2 else "manual"
    results = parse_text_file(path, source)
    print(json.dumps(results, indent=2))
    print(f"\nParsed {len(results)} items from {path}")
