
"""
ACMS Clothing Competitor Price Search
Standalone prototype - Budget: 0 BDT

Flow:
1. DuckDuckGo searches clothing products in Bangladesh.
2. Irrelevant products are filtered out.
3. Optional free OpenRouter model extracts prices.
4. Regex fallback works without an API key.
5. Every extracted price must literally exist in its source snippet.
6. Duplicate URLs and extreme outliers are removed.
7. Median competitor price is calculated.

Install:
    pip install fastapi uvicorn ddgs httpx

Optional:
    OPENROUTER_API_KEY=your_key
    OPENROUTER_MODEL=nvidia/nemotron-nano-9b-v2:free

Run:
    uv run uvicorn app.api.webapi:app --reload --port 8000

Test:
    python test_clothing_prices.py
"""

import asyncio
import json
import os
import re
import statistics
import html

from typing import Optional
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from fastapi import APIRouter
from pydantic import BaseModel, Field


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

OPENROUTER_API_KEY = (
    os.getenv("OPENROUTER_API_KEY_1ST")
    or os.getenv("OPENROUTER_API_KEY_1st")
    or ""
)

OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3-ultra-550b-a55b:free"
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


# Clothing-focused Bangladeshi sellers.
CLOTHING_SITES = {
    "daraz.com.bd": "Daraz",
    "sareebangladesh.com": "Saree Bangladesh",
    "noborupa.com": "Noborupa",
    "dressup.com.bd": "Dress Up",
    "smartdeal.com.bd": "SmartDeal",
    "smarteshopbd.com": "Smart Eshop BD",
    "aarong.com": "Aarong",
    "kaykraft.com": "Kay Kraft",
    "yellowclothing.net": "Yellow",
    "lubnan.com.bd": "Lubnan",
    "ecstasybd.com": "Ecstasy",
}


router = APIRouter(prefix="/api")


# ---------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------

class SearchRequest(BaseModel):

    product_name: str

    brand: Optional[str] = None

    category: Optional[str] = None

    our_price: Optional[float] = Field(
        None,
        description="Our selling price in BDT."
    )

    max_results: int = Field(
        15,
        ge=5,
        le=30
    )


class Offer(BaseModel):

    seller: str

    product_title: str

    price_bdt: float

    url: str


class SearchResponse(BaseModel):

    query: str

    offers: list[Offer]

    median_price_bdt: Optional[float]

    min_price_bdt: Optional[float]

    max_price_bdt: Optional[float]

    our_price_vs_median_pct: Optional[float]

    method: str

    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------
# CLOTHING PRODUCT CLASSIFICATION
# ---------------------------------------------------------

# Each category has search terms and matching product names.
CLOTHING_CATEGORIES = {

    "saree": [
        "saree",
        "sharee",
        "sari",
    ],

    "hijab": [
        "hijab",
        "hijab scarf",
        "head scarf",
    ],

    "kurti": [
        "kurti",
        "kurta",
    ],

    "three piece": [
        "three piece",
        "three-piece",
        "3 piece",
        "3-piece",
        "salwar kameez",
        "salwar suit",
    ],

    "abaya": [
        "abaya",
        "burqa",
    ],

    "panjabi": [
        "panjabi",
        "punjabi",
        "kurta",
    ],

    "shirt": [
        "shirt",
        "t-shirt",
        "tshirt",
        "polo shirt",
    ],

    "trouser": [
        "chino",
        "chinos",
        "trouser",
        "pants",
        "jeans",
        "leggings",
        "palazzo",
    ],

    "dress": [
        "dress",
        "gown",
        "frock",
    ],

    "dupatta": [
        "dupatta",
        "orna",
        "orhna",
        "scarf",
    ],

    "blouse": [
        "blouse",
    ],

    "lehenga": [
        "lehenga",
        "lehengha",
    ],

    "fabric": [
        "fabric",
        "cloth",
        "cotton fabric",
    ],
}


# Products that must never enter clothing results.
NON_CLOTHING_KEYWORDS = {

    "monitor",
    "keyboard",
    "mouse",
    "computer",
    "laptop",
    "desktop",
    "processor",
    "cpu",
    "gpu",
    "graphics card",
    "motherboard",
    "power supply",
    "psu",
    "ram",
    "ssd",
    "hard disk",
    "webcam",
    "headset",
    "earphone",
    "headphone",
    "speaker",
    "printer",
    "router",
    "wifi router",
    "cooler",
    "fan",
    "room heater",
    "water heater",
    "ups",
    "graphics card",
    "gaming chair",
    "smartphone",
    "mobile phone",
    "tablet",
}


# ---------------------------------------------------------
# PRICE EXTRACTION
# ---------------------------------------------------------

BN_DIGITS = str.maketrans(
    "০১২৩৪৫৬৭৮৯",
    "0123456789"
)


PRICE_RE = re.compile(
    r"(?:৳|tk\.?|bdt|taka)\s*([0-9০-৯][0-9০-৯,]*(?:\.[0-9]+)?)"
    r"|([0-9০-৯][0-9০-৯,]*(?:\.[0-9]+)?)\s*(?:৳|tk\b|bdt|taka)",
    re.IGNORECASE
)


def _to_price(value: object) -> Optional[float]:
    if value is None:
        return None
    raw = str(value).translate(BN_DIGITS).replace(",", "").strip()
    try:
        price = float(raw)
    except (TypeError, ValueError):
        return None
    return price if 50 <= price <= 5_000_000 else None


def parse_prices(text: str) -> list[float]:
    text = html.unescape(str(text or "")).translate(BN_DIGITS)
    prices = []
    for match in PRICE_RE.finditer(text):
        price = _to_price(match.group(1) or match.group(2))
        if price is not None:
            prices.append(price)
    return prices


def _walk_jsonld(value):
    """Yield dictionaries recursively from Product/Offer JSON-LD."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_jsonld(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_jsonld(child)


def extract_page_prices(page: str) -> list[float]:
    """
    Extract prices from product-page structured data.
    Only accepts explicit BDT/Taka values or JSON-LD offers marked BDT.
    """
    page = html.unescape(page or "")
    prices = []

    # JSON-LD is the most reliable source on ecommerce product pages.
    scripts = re.findall(
        r'<script[^>]*type=["\\\']application/ld\+json["\\\'][^>]*>(.*?)</script>',
        page,
        flags=re.I | re.S,
    )
    for script in scripts:
        try:
            data = json.loads(script.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in _walk_jsonld(data):
            if str(obj.get("@type", "")).lower() not in {"offer", "aggregateoffer"}:
                continue
            currency = str(obj.get("priceCurrency", "")).upper()
            if currency != "BDT":
                continue
            for key in ("price", "lowPrice", "highPrice"):
                price = _to_price(obj.get(key))
                if price is not None:
                    prices.append(price)

    # Common ecommerce metadata, accepted only when currency metadata says BDT.
    currency_matches = re.findall(
        r'<meta[^>]+(?:itemprop|property)=["\\\'](?:priceCurrency|product:price:currency)["\\\'][^>]+content=["\\\']([^"\\\']+)',
        page,
        flags=re.I,
    )
    has_bdt_meta = any(c.upper() == "BDT" for c in currency_matches)
    if has_bdt_meta:
        meta_prices = re.findall(
            r'<meta[^>]+(?:itemprop|property)=["\\\'](?:price|product:price:amount)["\\\'][^>]+content=["\\\']([^"\\\']+)',
            page,
            flags=re.I,
        )
        for raw in meta_prices:
            price = _to_price(raw)
            if price is not None:
                prices.append(price)

    # Visible text prices with an explicit currency marker.
    prices.extend(parse_prices(re.sub(r"<[^>]+>", " ", page)))
    return list(dict.fromkeys(prices))



# ---------------------------------------------------------
# TEXT HELPERS
# ---------------------------------------------------------

def normalize(text: str) -> str:

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9৳]+",
        " ",
        text
    )

    return " ".join(text.split())


def contains_keyword(text: str, keyword: str) -> bool:

    text = normalize(text)
    keyword = normalize(keyword)

    return bool(
        re.search(
            r"\b" + re.escape(keyword) + r"\b",
            text
        )
    )


# ---------------------------------------------------------
# CATEGORY DETECTION
# ---------------------------------------------------------

def get_product_keywords(req: SearchRequest) -> list[str]:

    """
    Determine relevant clothing terms from product name/category.

    Example:
        Georgette Saree -> saree, sharee, sari
        Premium Hijab -> hijab, hijab scarf
        Cotton Three Piece -> three piece, salwar kameez
    """

    search_text = normalize(
        f"{req.product_name} {req.category or ''}"
    )

    keywords = []

    for category, terms in CLOTHING_CATEGORIES.items():

        if contains_keyword(search_text, category):

            keywords.extend(terms)

        elif any(
            contains_keyword(search_text, term)
            for term in terms
        ):

            keywords.extend(terms)

    # Remove duplicate keywords.
    return list(dict.fromkeys(keywords))


# ---------------------------------------------------------
# CLOTHING RELEVANCE FILTER
# ---------------------------------------------------------

def is_relevant_clothing(
    req: SearchRequest,
    result: dict
) -> bool:

    """
    Reject unrelated products before price extraction.

    Product title and URL are prioritized because search
    snippets can contain unrelated aggregated content.
    """

    title = normalize(result.get("title", ""))

    url = normalize(result.get("url", ""))

    body = normalize(result.get("body", ""))

    # The title and URL determine the product identity.
    identity = f"{title} {url}"

    # Reject obvious non-clothing products.
    for keyword in NON_CLOTHING_KEYWORDS:

        if contains_keyword(identity, keyword):
            return False

    keywords = get_product_keywords(req)

    # If we cannot identify a clothing product type,
    # reject rather than accepting random search results.
    if not keywords:
        return False

    # Require at least one relevant product keyword
    # in the result title or URL.
    relevant = any(
        contains_keyword(identity, keyword)
        for keyword in keywords
    )

    if not relevant:
        return False

    return True


# ---------------------------------------------------------
# SELLER DETECTION
# ---------------------------------------------------------

def seller_from_url(url: str) -> str:

    host = (
        urlparse(url).hostname or ""
    ).lower()

    host = host.removeprefix("www.")

    for domain, name in CLOTHING_SITES.items():

        if host == domain or host.endswith("." + domain):
            return name

    return host or "Unknown seller"


# ---------------------------------------------------------
# SEARCH QUERY GENERATION
# ---------------------------------------------------------

def build_queries(req: SearchRequest) -> list[str]:

    base = " ".join(
        x for x in [
            req.brand,
            req.product_name
        ]
        if x
    )

    keywords = get_product_keywords(req)

    queries = [
        f'"{base}" price Bangladesh',
        f'"{base}" price BDT online',
        f'"{base}" clothing shop Bangladesh',
    ]

    # Search relevant clothing sellers instead of electronics stores.
    sites = [
        "daraz.com.bd",
        "sareebangladesh.com",
        "noborupa.com",
        "dressup.com.bd",
        "smartdeal.com.bd",
    ]

    for site in sites:

        queries.append(
            f'"{base}" site:{site}'
        )

    return queries


# ---------------------------------------------------------
# DUCKDUCKGO SEARCH
# ---------------------------------------------------------

def ddg_search(
    queries: list[str],
    per_query: int
) -> list[dict]:

    from ddgs import DDGS

    seen = set()

    results = []

    with DDGS() as ddgs:

        for query in queries:

            try:

                search_results = ddgs.text(
                    query,
                    region="bd-en",
                    safesearch="moderate",
                    max_results=per_query
                )

                for result in search_results:

                    url = (
                        result.get("href")
                        or result.get("url")
                    )

                    if not url:
                        continue

                    if url in seen:
                        continue

                    seen.add(url)

                    results.append({

                        "title": result.get("title", ""),

                        "body": result.get("body", ""),

                        "url": url,

                    })

            except Exception:
                # Continue with other queries if one fails.
                continue

    return results


# ---------------------------------------------------------
# PRODUCT PAGE PRICE ENRICHMENT
# ---------------------------------------------------------

async def enrich_results_from_product_pages(
    results: list[dict],
    max_pages: int = 20,
) -> list[dict]:
    """
    Visit candidate product URLs because DDG snippets frequently omit prices.
    Extract explicit BDT prices from JSON-LD, ecommerce metadata, or visible text.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    semaphore = asyncio.Semaphore(5)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(12.0),
        follow_redirects=True,
        headers=headers,
    ) as client:

        async def fetch_one(result):
            async with semaphore:
                try:
                    response = await client.get(result["url"])
                    if response.status_code >= 400:
                        result["page_error"] = f"HTTP {response.status_code}"
                        return result
                    content_type = response.headers.get("content-type", "").lower()
                    if "html" not in content_type and "<html" not in response.text[:500].lower():
                        return result
                    page_prices = extract_page_prices(response.text[:2_000_000])
                    if page_prices:
                        result["page_prices_bdt"] = page_prices
                        result["page_text"] = re.sub(
                            r"\\s+", " ",
                            re.sub(r"<[^>]+>", " ", response.text[:500_000])
                        )[:12000]
                    return result
                except Exception as exc:
                    result["page_error"] = type(exc).__name__
                    return result

        selected = results[:max_pages]
        fetched = await asyncio.gather(*(fetch_one(r) for r in selected))
        return fetched + results[max_pages:]


# ---------------------------------------------------------
# OPTIONAL LLM EXTRACTION
# ---------------------------------------------------------

async def llm_extract(
    req: SearchRequest,
    results: list[dict]
) -> list[dict]:

    listing = "\n".join(

        f"[{i}] "
        f"{result['title']} | "
        f"{result['body'][:300]} | "
        f"Page BDT prices: {result.get('page_prices_bdt', [])} | "
        f"{result['url']}"

        for i, result in enumerate(results)

    )

    prompt = f"""
You are a clothing product price extraction system.

Target product:
{req.product_name}

Category:
{req.category or "Clothing"}

Brand:
{req.brand or "Not specified"}

Currency:
Bangladeshi Taka (BDT).

Your task:

1. Identify results selling the same or a very similar clothing product.
2. Ignore electronics, accessories unrelated to clothing,
   unrelated products and category pages without a clear offer.
3. Extract prices only when explicitly visible in the result.
4. Never guess or calculate prices.
5. Ignore prices in foreign currencies.
6. Use the exact source result index.
7. If uncertain, skip the result.

Return ONLY a JSON array.

Format:

[
    {{
        "index": 0,
        "product_title": "Product name",
        "price_bdt": 1200
    }}
]

Search results:

{listing}
"""

    headers = {

        "Authorization": f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type": "application/json",

    }

    payload = {

        "model": OPENROUTER_MODEL,

        "temperature": 0,

        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],

    }

    async with httpx.AsyncClient(timeout=60) as client:

        response = await client.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload
        )

        if response.is_error:
            # Keep enough provider detail to diagnose invalid model/key/quota errors.
            detail = response.text[:500].replace("\\n", " ")
            raise RuntimeError(
                f"OpenRouter HTTP {response.status_code}: {detail}"
            )

        payload_data = response.json()
        choices = payload_data.get("choices") or []
        if not choices:
            raise RuntimeError(
                f"OpenRouter returned no choices: {str(payload_data)[:500]}"
            )
        content = choices[0].get("message", {}).get("content") or ""

    # Remove reasoning tags if returned.
    content = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.S
    )

    # Extract JSON array.
    match = re.search(
        r"\[.*\]",
        content,
        flags=re.S
    )

    if not match:
        return []

    data = json.loads(match.group(0))

    if not isinstance(data, list):
        return []

    return data


# ---------------------------------------------------------
# REGEX FALLBACK
# ---------------------------------------------------------

def regex_extract(results: list[dict]) -> list[dict]:

    items = []

    for index, result in enumerate(results):

        text = (
            result["title"]
            + " "
            + result["body"]
            + " "
            + result.get("page_text", "")
        )

        prices = result.get("page_prices_bdt") or parse_prices(text)

        if not prices:
            continue

        items.append({

            "index": index,

            "product_title": result["title"],

            "price_bdt": prices[0],

        })

    return items


# ---------------------------------------------------------
# PRICE VALIDATION
# ---------------------------------------------------------

def validate(
    items: list[dict],
    results: list[dict]
) -> list[Offer]:

    offers = []

    seen_urls = set()

    for item in items:

        try:

            index = int(item["index"])

            price = float(item["price_bdt"])

            result = results[index]

        except (
            KeyError,
            ValueError,
            IndexError,
            TypeError
        ):

            continue

        # Validate that the price literally exists
        # in the original search result.
        source_text = (
            result["title"]
            + " "
            + result["body"]
        )

        found_prices = (
            parse_prices(source_text)
            + result.get("page_prices_bdt", [])
        )

        if not any(abs(price - found) < 1 for found in found_prices):
            continue

        # Prevent duplicate URLs.
        url = result["url"]

        if url in seen_urls:
            continue

        seen_urls.add(url)

        offers.append(

            Offer(

                seller=seller_from_url(url),

                product_title=str(
                    item.get("product_title")
                    or result["title"]
                )[:200],

                price_bdt=price,

                url=url,

            )

        )

    return offers


# ---------------------------------------------------------
# OUTLIER REMOVAL
# ---------------------------------------------------------

def drop_outliers(
    offers: list[Offer]
) -> tuple[list[Offer], int]:

    if len(offers) < 4:
        return offers, 0

    median = statistics.median(
        offer.price_bdt
        for offer in offers
    )

    # Remove extreme prices.
    kept = [

        offer

        for offer in offers

        if 0.4 * median <= offer.price_bdt <= 2.5 * median

    ]

    removed = len(offers) - len(kept)

    return kept, removed


# ---------------------------------------------------------
# EMPTY RESPONSE HELPER
# ---------------------------------------------------------

def empty_response(
    req: SearchRequest,
    notes: list[str]
) -> SearchResponse:

    return SearchResponse(

        query=req.product_name,

        offers=[],

        median_price_bdt=None,

        min_price_bdt=None,

        max_price_bdt=None,

        our_price_vs_median_pct=None,

        method="none",

        notes=notes,

    )


# ---------------------------------------------------------
# MAIN API ENDPOINT
# ---------------------------------------------------------

@router.post(
    "/competitor-price-search",
    response_model=SearchResponse
)
async def competitor_price_search(
    req: SearchRequest
) -> SearchResponse:

    notes = []

    # 1. Validate product category.
    keywords = get_product_keywords(req)

    if not keywords:

        return empty_response(
            req,
            [
                "Could not identify a supported clothing category.",
                "Specify a category such as saree, hijab, kurti or three piece."
            ]
        )

    # 2. Generate clothing-specific queries.
    queries = build_queries(req)

    # 3. Search DuckDuckGo.
    per_query = max(
        5,
        req.max_results // len(queries)
    )

    try: 

        raw_results = await asyncio.to_thread(
            ddg_search,
            queries,
            per_query
        )

    except Exception as error:

        return empty_response(
            req,
            [
                f"DuckDuckGo search failed: {type(error).__name__}: {error}"
            ]
        )

    if not raw_results:

        return empty_response(
            req,
            [
                "No search results returned.",
                "DuckDuckGo may be rate-limiting requests. Try again later."
            ]
        )

    # 4. Filter irrelevant products.
    results = [

        result

        for result in raw_results

        if is_relevant_clothing(req, result)

    ]

    notes.append(
        f"Raw search results: {len(raw_results)}"
    )

    notes.append(
        f"Relevant clothing results: {len(results)}"
    )

    if not results:

        return empty_response(
            req,
            notes + [
                "No relevant clothing products found.",
                "Try a more specific product name or category."
            ]
        )

    # Limit results after filtering, then visit product pages.
    results = results[:req.max_results * 2]

    results = await enrich_results_from_product_pages(results)

    pages_with_prices = sum(
        bool(result.get("page_prices_bdt"))
        for result in results
    )
    notes.append(f"Product pages with explicit BDT prices: {pages_with_prices}")

    # 5. Extract prices.
    method = "regex"

    items = []

    if OPENROUTER_API_KEY:

        try:

            items = await llm_extract(
                req,
                results
            )

            if items:

                method = f"llm:{OPENROUTER_MODEL}"

            else:

                notes.append(
                    "LLM returned no usable offers; used regex fallback."
                )

        except Exception as error:

            notes.append(
                f"LLM failed ({type(error).__name__}); used regex fallback."
            )

    else:

        notes.append(
            "OPENROUTER_API_KEY not configured; using regex fallback."
        )

    # Fallback when no LLM results are available.
    if not items:

        items = regex_extract(results)

        method = "regex"

    # 6. Validate extracted prices.
    offers = validate(
        items,
        results
    )

    # 7. Remove duplicates and extreme outliers.
    offers, removed = drop_outliers(offers)

    if removed:

        notes.append(
            f"Removed {removed} extreme price outlier(s)."
        )

    # 8. Calculate statistics.
    prices = [
        offer.price_bdt
        for offer in offers
    ]

    median = (
        statistics.median(prices)
        if prices
        else None
    )

    minimum = (
        min(prices)
        if prices
        else None
    )

    maximum = (
        max(prices)
        if prices
        else None
    )

    # 9. Compare our price with competitor median.
    comparison = None

    if median is not None and req.our_price is not None:

        if median > 0:

            comparison = round(
                (
                    (req.our_price - median)
                    / median
                ) * 100,
                1
            )

    if not offers:

        notes.append(
            "No valid priced clothing offers found."
        )

    if method == "regex" and offers:

        notes.append(
            "Regex extraction may select an unrelated price from a mixed snippet. "
            "Manually verify offers before using the median."
        )

    # 10. Return response.
    return SearchResponse(

        query=req.product_name,

        offers=sorted(
            offers,
            key=lambda offer: offer.price_bdt
        ),

        median_price_bdt=median,

        min_price_bdt=minimum,

        max_price_bdt=maximum,

        our_price_vs_median_pct=comparison,

        method=method,

        notes=notes,

    )


# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------

@router.get("/competitor-health")
def health():

    return {

        "ok": True,

        "service": "ACMS Clothing Competitor Price Search",

        "llm_enabled": bool(OPENROUTER_API_KEY),

        "model": OPENROUTER_MODEL,

        "supported_categories": list(
            CLOTHING_CATEGORIES.keys()
        ),

    }
