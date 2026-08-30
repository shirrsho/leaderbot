"""
View and export flagged leads.

Usage:
    python review.py                      # print leads to terminal
    python review.py --min-confidence 0.6
    python review.py --export leads.csv   # export to CSV
"""
import argparse
import csv
from storage.db import fetch_leads


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--export", help="path to export CSV to")
    args = parser.parse_args()

    leads = fetch_leads(min_confidence=args.min_confidence, only_leads=True)

    if args.export:
        if not leads:
            print("No leads to export.")
            return
        with open(args.export, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=leads[0].keys())
            writer.writeheader()
            writer.writerows(leads)
        print(f"Exported {len(leads)} leads to {args.export}")
        return

    print(f"{len(leads)} leads (confidence >= {args.min_confidence}):\n")
    for l in leads:
        print(f"[{l['confidence']:.2f}] {l['source']} | {l['author']} | {l['intent']} | {l['urgency']}")
        print(f"  {l['text'][:150].strip()}...")
        print(f"  Reason: {l['reason']}")
        print(f"  URL: {l['post_url']}")
        print()


if __name__ == "__main__":
    main()
