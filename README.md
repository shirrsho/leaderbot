# leaderbot

Collect posts from Reddit (or manually pasted text from Facebook groups etc.)
and use Groq's free LLM API to flag potential leads for your product/service.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Your Groq API key is already set in `.env` (GROQ_API_KEY). `.env` is gitignored — never commit it.

## Web UI (recommended)

A browser frontend that wires everything together — source selection,
connection test, product description, run button, results table, CSV export.

```bash
source venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open **http://127.0.0.1:3500** in your browser.

Or with Docker:
```bash
cp .env.example .env   # fill in GROQ_API_KEY
docker compose -f docker-compose.dev.yml up --build
```

The UI shows the active Groq model and whether your key is detected, lets you
switch between **Reddit** and **Manual paste**, test the Reddit connection
before running, and export flagged leads to CSV.

## Command-line usage

### Reddit

No API credentials needed — the collector uses Reddit's public read-only
JSON endpoints. This works from a normal residential connection; it does
**not** work from cloud/datacenter IPs (Reddit blocks those with a 403).

**Step 1 — confirm Reddit is reachable from your machine:**
```bash
python collectors/reddit_collector.py --test smallbusiness
```
- `OK — reachable` → you're good, continue.
- `BLOCKED / failed` → your network/IP is blocked; try another network (e.g.
  phone hotspot) or use manual paste (see below).

**Step 2 — run a full collection + lead extraction:**
```bash
python run.py reddit smallbusiness --product "a CRM tool for small teams" --limit 50
python review.py --export leads.csv
```

Optional: set a descriptive User-Agent with your reddit username in `.env`
(`REDDIT_USER_AGENT=leaderbot/0.1 by u/your_username`).

If your IP ever gets blocked, fall back to manual paste — browse the
subreddit yourself, copy posts into a `.txt` file (one per block, separated
by `---`), then:
```bash
python run.py manual reddit_posts.txt reddit --product "a CRM tool for small teams"
```

### Facebook / other groups (manual paste)
Facebook's API doesn't expose group content, and scraping FB violates their
ToS. Instead: copy/paste post text into a `.txt` file, separating posts with
`---`:

```
Author: Jane Doe
Looking for a good accountant for my small business in Austin, any recs?
---
Author: John Smith
Just posting weekend photos.
---
```

Then run:
```bash
python run.py manual posts.txt facebook --product "a CRM tool for small teams"
```

### Review / export results
```bash
python review.py                          # print to terminal
python review.py --min-confidence 0.7
python review.py --export leads.csv       # export to CSV
```

## Notes
- Free Groq tier has rate limits; the extractor batches posts (15/call by
  default) and sleeps briefly between calls.
- Nothing here auto-contacts anyone — review flagged leads yourself before
  reaching out, both for quality and to respect each platform's rules.
- Leads are stored in `leads.db` (SQLite, gitignored).
# leaderbot
