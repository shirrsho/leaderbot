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

### Maps → Companies (B2B lead finder)

The **🗺️ Maps → Companies** tab finds businesses on the map by type + location,
then the AI shortlists which ones are probable customers for what you sell —
with their details (phone/website/address/map link) and a reason for each.

- **Business type / category:** pick from the dropdown (130+ types grouped by
  industry) or choose "Other" to type a custom one. Dropdown categories are
  mapped to real OSM tags and queried via the Overpass API for reliable,
  complete results; custom text uses free-text search.
- **Location:** e.g. `Dhaka, Bangladesh`, `Austin, Texas`
- **What you sell** (the product field): the AI judges fit against this

Data comes from **OpenStreetMap** (free, no key). Coverage varies by area —
big cities give the best results; phone/website show only when the business
added them to OSM. Results are stored in the `companies` table and export to
CSV via the same Export button.

> Want richer data (phone/website/ratings on nearly every business)? A Google
> Places API key can be wired in as an alternative provider — ask when ready.

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

## Deployment

Production runs on the Advergo VPS as the Hostinger Docker Manager project
**`redelevators-leaderbot`**, in `/docker/redelevators-leaderbot/`: `docker-compose.yml` (this
repo's `docker-compose.prod.yml`) and `.env` (the panel's Environment box). Visitors reach it only
through the Red Elevators leaderbot Cloudflare Tunnel (`leaderbot.redelevators.com` →
`http://web:3000`). Leads are kept in SQLite at `/app/data/leads.db`, on the volume
`redelevators-leaderbot_leaderbot-data`.

Every push to `main` runs `.github/workflows/deploy.yml`: after the checks pass it builds the
image, pushes `itzwasik/leaderbot:sha-<commit>` (and `:latest`) to Docker Hub, copies
`docker-compose.prod.yml` to the server as `docker-compose.yml` with the image pinned to that
build, and runs `ops/deploy.sh` there (copy `leads.db` to
`backups/prod/leaderbot-predeploy-<time>.db`, restart, wait until healthy, check
`http://127.0.0.1:6002/` on the VPS). Deploys never write `.env`.

| Production setting (panel Environment) | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq API key (required) |
| `GROQ_MODEL` | Groq model; optional, defaults to `openai/gpt-oss-120b` |
| `REDDIT_COOKIE` | Logged-in Reddit cookie so Reddit requests aren't blocked; optional |
| `REDDIT_USER_AGENT` | User-Agent override for Reddit/OpenStreetMap requests; optional |
| `CLOUDFLARE_TUNNEL_TOKEN` | The leaderbot tunnel's token |

A new setting must be added to both the panel's Environment box and `docker-compose.prod.yml`: the
panel rejects `env_file`, so each one is listed there explicitly.

The image has no build-time settings.

GitHub secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `VPS_HOST`, `VPS_SSH_PORT`,
`VPS_SSH_USER` (`root`) and `VPS_SSH_KEY`.

Rolling back: in the panel, set the `image:` tag in the YAML editor to the previous `sha-…` and
press Deploy (the previous file is also kept on the server as `backups/docker-compose.previous.yml`).
To restore the data, stop the project and copy a `backups/prod/leaderbot-predeploy-*.db` file over
`leads.db` in the volume.
