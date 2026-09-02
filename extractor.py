"""Send batches of posts to Groq's API and extract structured leads."""
import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
API_KEY = os.environ["GROQ_API_KEY"]
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM_PROMPT = """You are a lead-extraction assistant.

You will be given a numbered list of social media posts/comments. Your job:
identify which ones show someone who might be a LEAD for {product_description}.

A lead is someone who:
- is asking for a recommendation, tool, or service in this space
- is complaining about a problem this product/service solves
- is comparing options and undecided
- explicitly says they are looking to buy/hire/switch

Return ONLY valid JSON (no markdown, no commentary) matching this schema:
{{
  "leads": [
    {{
      "post_id": "<the id given for this post>",
      "is_lead": true,
      "confidence": 0.0-1.0,
      "reason": "short explanation grounded in the text",
      "intent": "seeking_recommendation | complaining | comparing | ready_to_buy | other",
      "urgency": "low | medium | high"
    }}
  ]
}}

Include an entry for EVERY post, even if is_lead is false (confidence should be low then).
Do not invent details not present in the text.
"""


COMPANY_PROMPT = """You are a B2B sales analyst.

You will be given a numbered list of companies/businesses found on a map,
each with whatever details are available (name, category, address, phone,
website). Your job: decide which ones are PROBABLE CUSTOMERS for what we
sell: {product_description}.

A probable customer is a business whose type, size, or context suggests they
would realistically need or benefit from this product/service.

Return ONLY valid JSON (no markdown, no commentary) matching this schema:
{{
  "companies": [
    {{
      "company_id": "<the id given for this company>",
      "is_customer": true,
      "confidence": 0.0-1.0,
      "reason": "why this business is (or isn't) a likely customer, grounded in its type/details",
      "fit_signals": "short comma-separated cues, e.g. 'restaurant, likely needs POS, has website'"
    }}
  ]
}}

Include an entry for EVERY company, even if is_customer is false (low
confidence then). Do not invent details not present in the data.
"""


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _call_groq(system_prompt: str, user_content: str):
    """Single Groq JSON-mode call. Returns parsed dict, or None on error."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"Groq API error {resp.status_code}: {resp.text[:300]}")
        return None
    content = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON from model output: {content[:300]}")
        return None


def shortlist_companies(companies: list, product_description: str, batch_size: int = 15,
                         sleep_between_calls: float = 1.0):
    """
    companies: list of dicts with at least {company_id, name} and optionally
               {category, address, phone, website}.
    Returns: list of dicts merging original company fields + AI verdict fields
             (is_customer, confidence, reason, fit_signals).
    """
    all_results = []
    id_lookup = {str(c["company_id"]): c for c in companies}
    system = COMPANY_PROMPT.format(product_description=product_description)

    for batch in _chunk(companies, batch_size):
        user_content = "\n\n".join(
            "company_id: {id}\nname: {name}\ncategory: {cat}\naddress: {addr}\n"
            "phone: {phone}\nwebsite: {web}".format(
                id=c["company_id"], name=c.get("name", ""), cat=c.get("category", ""),
                addr=c.get("address", ""), phone=c.get("phone", ""), web=c.get("website", ""))
            for c in batch
        )
        parsed = _call_groq(system, user_content)
        if parsed:
            for verdict in parsed.get("companies", []):
                original = id_lookup.get(str(verdict.get("company_id")))
                if not original:
                    continue
                all_results.append({
                    **original,
                    "is_customer": bool(verdict.get("is_customer")),
                    "confidence": float(verdict.get("confidence", 0)),
                    "reason": verdict.get("reason", ""),
                    "fit_signals": verdict.get("fit_signals", ""),
                })
        time.sleep(sleep_between_calls)

    return all_results


def extract_leads(items: list, product_description: str, batch_size: int = 15,
                   sleep_between_calls: float = 1.0):
    """
    items: list of dicts with at least {post_id, text, author, url}
    Returns: list of dicts merging original item fields + LLM verdict fields.
    """
    all_results = []
    id_lookup = {item["post_id"]: item for item in items}

    for batch in _chunk(items, batch_size):
        user_content = "\n\n".join(
            f'post_id: {it["post_id"]}\nauthor: {it["author"]}\ntext: {it["text"]}'
            for it in batch
        )

        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(product_description=product_description)},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )

        if resp.status_code != 200:
            print(f"Groq API error {resp.status_code}: {resp.text[:300]}")
            time.sleep(sleep_between_calls)
            continue

        content = resp.json()["choices"][0]["message"]["content"]

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON from model output: {content[:300]}")
            continue

        for verdict in parsed.get("leads", []):
            pid = verdict.get("post_id")
            original = id_lookup.get(str(pid)) or id_lookup.get(pid)
            if not original:
                continue
            all_results.append({
                **original,
                "is_lead": bool(verdict.get("is_lead")),
                "confidence": float(verdict.get("confidence", 0)),
                "reason": verdict.get("reason", ""),
                "intent": verdict.get("intent", "other"),
                "urgency": verdict.get("urgency", "low"),
            })

        time.sleep(sleep_between_calls)  # be gentle with free-tier rate limits

    return all_results
