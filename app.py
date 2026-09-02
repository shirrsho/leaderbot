"""
Flask backend + static frontend for leaderbot.

Run:
    source venv/bin/activate
    pip install -r requirements.txt   # (adds flask)
    python app.py
Then open http://127.0.0.1:3000 in your browser.
"""
import io
import csv
import os
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_file, send_from_directory
from dotenv import load_dotenv

from storage.db import (init_db, upsert_lead, fetch_leads,
                        get_cursor, set_cursor, clear_cursor,
                        upsert_company, fetch_companies)
from extractor import extract_leads, shortlist_companies, MODEL

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")


def _save(results):
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


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/config")
def config():
    return jsonify({"model": MODEL, "groq_key_set": bool(os.environ.get("GROQ_API_KEY"))})


@app.route("/api/test-reddit")
def test_reddit():
    sub = request.args.get("subreddit", "smallbusiness")
    from collectors.reddit_collector import _get, USER_AGENT
    try:
        data = _get(f"https://www.reddit.com/r/{sub}/new.json", params={"limit": 1}, retries=1)
        children = data.get("data", {}).get("children", [])
        if children:
            return jsonify({"ok": True, "user_agent": USER_AGENT,
                            "sample_title": children[0]["data"].get("title", "")})
        return jsonify({"ok": False, "error": "Reached endpoint but no posts (private/empty?)."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/run", methods=["POST"])
def run():
    body = request.get_json(force=True)
    mode = body.get("mode")
    product = (body.get("product") or "").strip()
    if not product:
        return jsonify({"error": "Product description is required."}), 400

    init_db()

    next_after = None
    reached_end = False
    try:
        if mode == "reddit":
            sub = (body.get("subreddit") or "").strip()
            if not sub:
                return jsonify({"error": "Subreddit name is required."}), 400
            limit = int(body.get("limit", 25))
            comments = int(body.get("comments_per_post", 2))
            start_fresh = bool(body.get("start_fresh"))

            cursor_key = f"reddit:{sub.lower()}"
            if start_fresh:
                clear_cursor(cursor_key)
                after = None
            else:
                after = get_cursor(cursor_key)

            from collectors.reddit_collector import collect_subreddit
            items, next_after = collect_subreddit(
                sub, limit=limit, comments_per_post=comments, after=after)

            # Save the new position so the next run continues from here.
            set_cursor(cursor_key, next_after)
            reached_end = next_after is None
        elif mode == "manual":
            raw = body.get("text") or ""
            label = (body.get("source_label") or "manual").strip()
            from collectors.manual_collector import parse_text
            items = parse_text(raw, label)
        else:
            return jsonify({"error": f"Unknown mode: {mode}"}), 400
    except Exception as e:
        return jsonify({"error": f"Collection failed: {e}"}), 500

    if not items:
        return jsonify({"collected": 0, "leads_found": 0, "leads": [],
                        "message": "No posts collected."})

    try:
        results = extract_leads(items, product_description=product)
    except Exception as e:
        return jsonify({"error": f"Groq extraction failed: {e}"}), 500

    _save(results)
    leads = [r for r in results if r["is_lead"]]
    leads.sort(key=lambda x: x["confidence"], reverse=True)

    posts_count = sum(1 for it in items if it.get("kind") == "post")
    comments_count = sum(1 for it in items if it.get("kind") == "comment")

    return jsonify({
        "collected": len(items),
        "posts": posts_count,
        "comments": comments_count,
        "processed": len(results),
        "leads_found": len(leads),
        "has_more": (mode == "reddit" and not reached_end),
        "reached_end": reached_end,
        "leads": [{
            "author": r["author"], "confidence": r["confidence"],
            "intent": r["intent"], "urgency": r["urgency"],
            "reason": r["reason"], "text": r["text"][:400],
            "url": r.get("url", ""), "source": r["source"],
            "created_utc": r.get("created_utc", 0),
        } for r in leads],
    })


@app.route("/api/maps", methods=["POST"])
def maps():
    body = request.get_json(force=True)
    business_type = (body.get("business_type") or "").strip()
    location = (body.get("location") or "").strip()
    product = (body.get("product") or "").strip()
    limit = int(body.get("limit", 25))

    if not business_type:
        return jsonify({"error": "Business type/category is required."}), 400
    if not location:
        return jsonify({"error": "Location is required."}), 400
    if not product:
        return jsonify({"error": "Product description is required."}), 400

    init_db()

    try:
        from collectors.maps_collector import search_companies
        found = search_companies(business_type, location, limit=limit)
    except Exception as e:
        return jsonify({"error": f"Map search failed: {e}"}), 500

    if not found:
        return jsonify({"found": 0, "customers_found": 0, "companies": [],
                        "message": "No businesses found. Try a broader type or a bigger city."})

    try:
        results = shortlist_companies(found, product_description=product)
    except Exception as e:
        return jsonify({"error": f"AI shortlisting failed: {e}"}), 500

    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        upsert_company({
            "company_id": r["company_id"], "name": r.get("name", ""),
            "category": r.get("category", ""), "address": r.get("address", ""),
            "phone": r.get("phone", ""), "website": r.get("website", ""),
            "lat": r.get("lat", ""), "lon": r.get("lon", ""),
            "source": r.get("source", "osm"),
            "is_customer": int(r["is_customer"]), "confidence": r["confidence"],
            "reason": r["reason"], "fit_signals": r.get("fit_signals", ""),
            "query": business_type, "location": location, "created_at": now,
        })

    customers = [r for r in results if r["is_customer"]]
    customers.sort(key=lambda x: x["confidence"], reverse=True)

    return jsonify({
        "found": len(found),
        "processed": len(results),
        "customers_found": len(customers),
        "companies": [{
            "name": r.get("name", ""), "category": r.get("category", ""),
            "address": r.get("address", ""), "phone": r.get("phone", ""),
            "website": r.get("website", ""), "confidence": r["confidence"],
            "reason": r["reason"], "fit_signals": r.get("fit_signals", ""),
            "lat": r.get("lat", ""), "lon": r.get("lon", ""),
        } for r in customers],
    })


@app.route("/api/companies")
def companies():
    min_conf = float(request.args.get("min_confidence", 0.5))
    return jsonify(fetch_companies(min_confidence=min_conf, only_customers=True))


@app.route("/api/companies/export")
def companies_export():
    min_conf = float(request.args.get("min_confidence", 0.5))
    rows = fetch_companies(min_confidence=min_conf, only_customers=True)
    if not rows:
        return jsonify({"error": "No companies to export."}), 404
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name="companies.csv")


@app.route("/api/leads")
def leads():
    min_conf = float(request.args.get("min_confidence", 0.5))
    return jsonify(fetch_leads(min_confidence=min_conf, only_leads=True))


@app.route("/api/export")
def export():
    min_conf = float(request.args.get("min_confidence", 0.5))
    rows = fetch_leads(min_confidence=min_conf, only_leads=True)
    if not rows:
        return jsonify({"error": "No leads to export."}), 404
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    mem = io.BytesIO(buf.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                     download_name="leads.csv")


if __name__ == "__main__":
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 3000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app.run(host=host, port=port, debug=debug)
