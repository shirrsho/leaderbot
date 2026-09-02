"""
Search businesses on the map by type/category + location, using OpenStreetMap.

Free, no API key. Two strategies:

1. Known dropdown categories -> mapped to real OSM tags (e.g. "dental clinic"
   -> amenity=dentist) and queried via the **Overpass API**, which searches by
   map tags. This is reliable and comprehensive (unlike free-text search, which
   is very sensitive to wording).

2. Custom free-text terms (anything not in TAG_MAP) -> fall back to Nominatim's
   free-text search.

Notes / limits:
- OSM business coverage varies by region: good in cities, sparse elsewhere.
  Phone/website are only present when someone added them to OSM.
- Overpass and Nominatim have fair-use limits; this module sends a real
  User-Agent and keeps requests modest.
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = os.environ.get("REDDIT_USER_AGENT") or \
    "leaderbot-maps/0.1 (personal B2B lead research)"

# Dropdown value -> list of OSM (key, value) tag filters. Multiple tags are OR'd.
TAG_MAP = {
    # Food & Drink
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "coffee shop": [("amenity", "cafe")],
    "bakery": [("shop", "bakery")],
    "bar": [("amenity", "bar")],
    "pub": [("amenity", "pub")],
    "fast food": [("amenity", "fast_food")],
    "food truck": [("amenity", "fast_food")],
    "catering service": [("craft", "caterer")],
    "ice cream shop": [("amenity", "ice_cream"), ("shop", "ice_cream")],
    "juice bar": [("amenity", "juice_bar")],
    "tea house": [("amenity", "cafe")],
    "sweet shop": [("shop", "confectionery")],
    # Retail
    "supermarket": [("shop", "supermarket")],
    "grocery store": [("shop", "grocery"), ("shop", "convenience")],
    "convenience store": [("shop", "convenience")],
    "clothing store": [("shop", "clothes")],
    "shoe store": [("shop", "shoes")],
    "jewelry store": [("shop", "jewelry")],
    "electronics store": [("shop", "electronics")],
    "mobile phone shop": [("shop", "mobile_phone")],
    "furniture store": [("shop", "furniture")],
    "hardware store": [("shop", "hardware"), ("shop", "doityourself")],
    "bookstore": [("shop", "books")],
    "stationery shop": [("shop", "stationery")],
    "florist": [("shop", "florist")],
    "gift shop": [("shop", "gift")],
    "pet store": [("shop", "pet")],
    "toy store": [("shop", "toys")],
    "sporting goods store": [("shop", "sports")],
    "optical shop": [("shop", "optician")],
    "cosmetics store": [("shop", "cosmetics"), ("shop", "chemist")],
    "pharmacy": [("amenity", "pharmacy")],
    # Health & Medical
    "hospital": [("amenity", "hospital")],
    "clinic": [("amenity", "clinic"), ("healthcare", "clinic")],
    "dental clinic": [("amenity", "dentist"), ("healthcare", "dentist")],
    "doctor's office": [("amenity", "doctors"), ("healthcare", "doctor")],
    "diagnostic lab": [("healthcare", "laboratory")],
    "physiotherapy center": [("healthcare", "physiotherapist")],
    "veterinary clinic": [("amenity", "veterinary")],
    "mental health clinic": [("healthcare", "psychotherapist")],
    "chiropractor": [("healthcare", "chiropractor")],
    "medical equipment supplier": [("shop", "medical_supply")],
    # Beauty & Wellness
    "beauty salon": [("shop", "beauty")],
    "hair salon": [("shop", "hairdresser")],
    "barber shop": [("shop", "hairdresser")],
    "spa": [("leisure", "spa"), ("shop", "beauty")],
    "nail salon": [("shop", "beauty")],
    "gym": [("leisure", "fitness_centre")],
    "fitness center": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "yoga studio": [("leisure", "fitness_centre")],
    "massage center": [("shop", "massage")],
    # Professional Services
    "law firm": [("office", "lawyer")],
    "accounting firm": [("office", "accountant")],
    "marketing agency": [("office", "advertising_agency")],
    "advertising agency": [("office", "advertising_agency")],
    "consulting firm": [("office", "consulting")],
    "real estate agency": [("office", "estate_agent")],
    "insurance agency": [("office", "insurance")],
    "architecture firm": [("office", "architect")],
    "engineering firm": [("office", "engineer")],
    "recruitment agency": [("office", "employment_agency")],
    # Technology
    "software company": [("office", "it")],
    "IT services company": [("office", "it")],
    "web design agency": [("office", "it")],
    "computer repair shop": [("shop", "computer")],
    "telecom company": [("office", "telecommunication")],
    # Education
    "school": [("amenity", "school")],
    "college": [("amenity", "college")],
    "university": [("amenity", "university")],
    "coaching center": [("amenity", "school")],
    "language school": [("amenity", "language_school")],
    "driving school": [("amenity", "driving_school")],
    "kindergarten": [("amenity", "kindergarten")],
    "library": [("amenity", "library")],
    "training institute": [("amenity", "school")],
    "music school": [("amenity", "music_school")],
    # Automotive
    "car dealership": [("shop", "car")],
    "auto repair shop": [("shop", "car_repair")],
    "car wash": [("amenity", "car_wash")],
    "tire shop": [("shop", "tyres")],
    "gas station": [("amenity", "fuel")],
    "motorcycle dealer": [("shop", "motorcycle")],
    "auto parts store": [("shop", "car_parts")],
    # Hospitality & Travel
    "hotel": [("tourism", "hotel")],
    "motel": [("tourism", "motel")],
    "guest house": [("tourism", "guest_house")],
    "hostel": [("tourism", "hostel")],
    "resort": [("tourism", "hotel")],
    "travel agency": [("shop", "travel_agency")],
    "tour operator": [("shop", "travel_agency")],
    # Construction & Home Services
    "general contractor": [("craft", "builder")],
    "plumber": [("craft", "plumber")],
    "electrician": [("craft", "electrician")],
    "painter": [("craft", "painter")],
    "interior designer": [("shop", "interior_decoration")],
    "landscaping service": [("craft", "gardener")],
    "roofing company": [("craft", "roofer")],
    # Manufacturing & Industrial
    "factory": [("man_made", "works")],
    "warehouse": [("building", "warehouse")],
    "wholesaler": [("shop", "trade")],
    "printing press": [("craft", "printer")],
    # Finance
    "bank": [("amenity", "bank")],
    "credit union": [("amenity", "bank")],
    "microfinance institution": [("office", "financial")],
    "investment firm": [("office", "financial")],
    "brokerage": [("office", "financial")],
    "money transfer service": [("amenity", "bureau_de_change")],
    # Entertainment & Recreation
    "cinema": [("amenity", "cinema")],
    "night club": [("amenity", "nightclub")],
    "bowling alley": [("leisure", "bowling_alley")],
    "amusement park": [("tourism", "theme_park")],
    "event venue": [("amenity", "events_venue")],
    "photography studio": [("craft", "photographer"), ("shop", "photo")],
    "art gallery": [("tourism", "gallery")],
    "museum": [("tourism", "museum")],
    "gaming center": [("leisure", "amusement_arcade")],
    # Logistics & Transport
    "courier service": [("office", "logistics")],
    "logistics company": [("office", "logistics")],
    "shipping company": [("office", "logistics")],
    "taxi service": [("amenity", "taxi")],
    "freight forwarder": [("office", "logistics")],
    # Agriculture
    "garden center": [("shop", "garden_centre")],
    "agricultural supplier": [("shop", "agrarian")],
    # Community & Other
    "NGO": [("office", "ngo"), ("office", "association")],
    "charity": [("office", "charity"), ("shop", "charity")],
    "community center": [("amenity", "community_centre")],
    "co-working space": [("amenity", "coworking_space"), ("office", "coworking")],
    "laundry service": [("shop", "laundry")],
    "dry cleaner": [("shop", "dry_cleaning")],
    "tailor": [("shop", "tailor"), ("craft", "tailor")],
    "funeral home": [("shop", "funeral_directors")],
    "storage facility": [("shop", "storage_rental")],
    "place of worship": [("amenity", "place_of_worship")],
}


def _geocode_bbox(location: str):
    """Return (south, west, north, east) bounding box for a place name."""
    resp = requests.get(NOMINATIM_URL, params={"q": location, "format": "jsonv2", "limit": 1},
                        headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RuntimeError(f"Could not find location: {location!r}")
    bb = data[0]["boundingbox"]   # [south, north, west, east] as strings
    time.sleep(1.1)
    return float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3])


def _address_from_tags(t: dict):
    parts = [t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:city"),
             t.get("addr:state"), t.get("addr:postcode")]
    return ", ".join(p for p in parts if p)


def _search_overpass(tags, location: str, limit: int):
    south, west, north, east = _geocode_bbox(location)
    bbox = f"{south},{west},{north},{east}"

    blocks = []
    for k, v in tags:
        for typ in ("node", "way"):
            blocks.append(f'{typ}["{k}"="{v}"]["name"]({bbox});')
    fetch = min(max(limit * 4, limit), 200)
    query = f"[out:json][timeout:40];({''.join(blocks)});out center tags {fetch};"

    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = requests.post(endpoint, data={"data": query},
                                 headers={"User-Agent": USER_AGENT}, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            last_err = e
            continue
    else:
        raise RuntimeError(f"Overpass query failed: {last_err}")

    companies = []
    seen = set()
    for el in data.get("elements", []):
        t = el.get("tags", {})
        name = t.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        lat = el.get("lat") or (el.get("center") or {}).get("lat", "")
        lon = el.get("lon") or (el.get("center") or {}).get("lon", "")
        # category = the matched tag that put it here
        category = next((f"{k}={t[k]}" for k, v in tags if t.get(k) == v), "")
        companies.append({
            "company_id": f"{el.get('type','')}-{el.get('id','')}",
            "name": name,
            "category": category,
            "address": _address_from_tags(t),
            "phone": t.get("phone") or t.get("contact:phone", ""),
            "website": t.get("website") or t.get("contact:website", ""),
            "lat": str(lat), "lon": str(lon),
            "source": "osm",
        })
        if len(companies) >= limit:
            break
    return companies


def _search_nominatim(business_type: str, location: str, limit: int):
    """Free-text fallback for custom terms not in TAG_MAP."""
    params = {
        "q": f"{business_type} in {location}".strip(),
        "format": "jsonv2", "limit": min(limit, 50),
        "extratags": 1, "addressdetails": 1, "namedetails": 1,
    }
    resp = requests.get(NOMINATIM_URL, params=params,
                        headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    companies = []
    for r in resp.json():
        extra = r.get("extratags") or {}
        nd = r.get("namedetails") or {}
        name = nd.get("name") or (r.get("display_name", "").split(",")[0]).strip()
        companies.append({
            "company_id": f"{r.get('osm_type','')}-{r.get('osm_id','')}",
            "name": name or "(unnamed)",
            "category": f"{r.get('class','')}/{r.get('type','')}".strip("/"),
            "address": r.get("display_name", ""),
            "phone": extra.get("phone") or extra.get("contact:phone", ""),
            "website": extra.get("website") or extra.get("contact:website", ""),
            "lat": r.get("lat", ""), "lon": r.get("lon", ""),
            "source": "osm",
        })
    time.sleep(1.1)
    return companies


def search_companies(business_type: str, location: str, limit: int = 25):
    """
    business_type: e.g. "restaurant", "dental clinic" (mapped to OSM tags), or
                   any custom text (free-text fallback).
    location: e.g. "Dhaka, Bangladesh", "Austin, Texas"
    Returns list of dicts:
      {company_id, name, category, address, phone, website, lat, lon, source}
    """
    key = business_type.strip().lower()
    tags = TAG_MAP.get(key)
    if tags:
        try:
            results = _search_overpass(tags, location, limit)
        except Exception as e:
            print(f"Overpass failed ({e}); falling back to free-text search.")
            results = []
        if results:
            return results
        # Overpass found nothing (sparse area / transient error) — free-text backup.
    return _search_nominatim(business_type, location, limit)


if __name__ == "__main__":
    import sys
    import json

    btype = sys.argv[1] if len(sys.argv) > 1 else "dental clinic"
    loc = sys.argv[2] if len(sys.argv) > 2 else "Austin, Texas"
    out = search_companies(btype, loc, limit=10)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nFound {len(out)} businesses for '{btype}' in '{loc}'")
