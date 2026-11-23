#!/usr/bin/env python3
"""Verbose, one-product diagnostic for ACMS competitor price search.

Run from the ACMS project root:
    uv run python test_competitor_search.py

Examples:
    uv run python test_competitor_search.py --product "Chino Pants - Beige" --category trouser
    uv run python test_competitor_search.py --product "Regular Fit Jeans - Light Blue" --category trouser --skip-llm

This script does NOT change the database. It can optionally call the ACMS HTTP endpoint
when --api-url is supplied. It reports which stage fails and writes competitor_search_debug.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


# Ensure imports resolve when this script is run from the ACMS project root.
PROJECT_ROOT = Path.cwd()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.agent import competitor_price_search as cps
except Exception as exc:
    print("ERROR: Could not import app.agent.competitor_price_search")
    print(f"{type(exc).__name__}: {exc}")
    print("Run this script from the ACMS project root, where the app/ folder exists.")
    raise SystemExit(1)


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def safe_domain(url: str) -> str:
    return urlparse(url).netloc or url


def compact(text: str, limit: int = 500) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def test_price_parser() -> dict[str, list[float]]:
    samples = {
        "৳1,350": "৳1,350",
        "Tk. 1,350": "Tk. 1,350",
        "BDT 1,350": "BDT 1,350",
        "1,350 taka": "1,350 taka",
        "Bengali digits": "৳ ১,৩৫০",
    }
    output: dict[str, list[float]] = {}
    for label, sample in samples.items():
        try:
            output[label] = cps.parse_prices(sample)
        except Exception as exc:
            output[label] = [f"ERROR: {type(exc).__name__}: {exc}"]  # type: ignore[list-item]
    return output


def run_search(queries: list[str], per_query: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    try:
        from ddgs import DDGS
    except Exception as exc:
        raise RuntimeError(
            "Cannot import ddgs. Install dependencies with: uv sync"
        ) from exc

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()

    # One DDGS client, but record errors per query instead of silently swallowing them.
    with DDGS() as ddgs:
        for query in queries:
            try:
                found = list(
                    ddgs.text(
                        query,
                        region="bd-en",
                        safesearch="moderate",
                        max_results=per_query,
                    )
                )
                print(f"[SEARCH OK] {len(found):2d} results | {query}")
                for row in found:
                    url = row.get("href") or row.get("url")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    results.append(
                        {
                            "title": row.get("title", ""),
                            "body": row.get("body", ""),
                            "url": url,
                        }
                    )
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                errors.append({"query": query, "error": message})
                print(f"[SEARCH ERROR] {query}\n              {message}")

    return results, errors


async def fetch_product_pages(results: list[dict[str, Any]], max_pages: int = 20) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    }
    semaphore = asyncio.Semaphore(4)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        follow_redirects=True,
        headers=headers,
    ) as client:

        async def fetch_one(result: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                debug: dict[str, Any] = {
                    "status": None,
                    "final_url": result["url"],
                    "content_type": "",
                    "html_chars": 0,
                    "page_price_count": 0,
                    "error": None,
                }
                try:
                    response = await client.get(result["url"])
                    debug["status"] = response.status_code
                    debug["final_url"] = str(response.url)
                    debug["content_type"] = response.headers.get("content-type", "")
                    debug["html_chars"] = len(response.text)

                    if response.status_code >= 400:
                        debug["error"] = f"HTTP {response.status_code}"
                    elif "html" not in debug["content_type"].lower() and "<html" not in response.text[:500].lower():
                        debug["error"] = "Response was not HTML"
                    else:
                        page = response.text[:2_000_000]
                        extractor = getattr(cps, "extract_page_prices", None)
                        if callable(extractor):
                            page_prices = extractor(page)
                        else:
                            # For older module versions, try visible page text only.
                            visible = re.sub(r"<[^>]+>", " ", page)
                            page_prices = cps.parse_prices(visible)

                        result["page_prices_bdt"] = page_prices
                        visible_text = re.sub(r"<[^>]+>", " ", response.text[:500_000])
                        result["page_text"] = compact(visible_text, 12000)
                        debug["page_price_count"] = len(page_prices)
                        if not page_prices:
                            debug["error"] = "Fetched HTML, but no explicit BDT price was extracted"

                except Exception as exc:
                    debug["error"] = f"{type(exc).__name__}: {exc}"

                result["_test_page"] = debug
                return result

        selected = results[:max_pages]
        return await asyncio.gather(*(fetch_one(row) for row in selected))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose ACMS clothing competitor price search")
    parser.add_argument("--product", default="Regular Fit Jeans - Light Blue")
    parser.add_argument("--category", default="trouser")
    parser.add_argument("--brand", default=None)
    parser.add_argument("--our-price", type=float, default=1350.0)
    parser.add_argument("--max-results", type=int, default=15)
    parser.add_argument("--skip-llm", action="store_true", help="Do not send an OpenRouter request")
    parser.add_argument("--output", default="competitor_search_debug.json")
    parser.add_argument("--api-url", default=None, help="Optional running ACMS base URL, e.g. http://127.0.0.1:8000")
    args = parser.parse_args()

    req = cps.SearchRequest(
        product_name=args.product,
        category=args.category,
        brand=args.brand,
        our_price=args.our_price,
        max_results=args.max_results,
    )

    print_section("0. IMPORTED MODULE / CONFIGURATION")
    print(f"Python:       {sys.version.split()[0]}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Module file:  {Path(cps.__file__).resolve()}")
    print(f"Product:      {req.product_name}")
    print(f"Category:     {req.category}")
    print(f"Keywords:     {cps.get_product_keywords(req)}")
    print(f"OpenRouter key loaded by module: {bool(getattr(cps, 'OPENROUTER_API_KEY', ''))}")
    print(f"OPENROUTER_API_KEY_1ST in env:   {bool(os.getenv('OPENROUTER_API_KEY_1ST') or os.getenv('OPENROUTER_API_KEY_1st'))}")
    print(f"GENAI_API_KEY in env:            {bool(os.getenv('GENAI_API_KEY'))}")
    print(f"OpenRouter model:                {getattr(cps, 'OPENROUTER_MODEL', '(unknown)')}")
    print(f"Updated page extractor loaded:   {callable(getattr(cps, 'extract_page_prices', None))}")

    print_section("1. PRICE PARSER SELF-TEST")
    parser_tests = test_price_parser()
    for label, result in parser_tests.items():
        print(f"{label:18} -> {result}")

    queries = cps.build_queries(req)
    per_query = max(5, req.max_results // max(1, len(queries)))
    print_section("2. SEARCH QUERIES")
    for index, query in enumerate(queries, 1):
        print(f"{index}. {query}")

    print_section("3. DUCKDUCKGO SEARCH")
    try:
        raw_results, search_errors = run_search(queries, per_query)
    except Exception as exc:
        print(f"SEARCH SETUP FAILED: {type(exc).__name__}: {exc}")
        return 2

    print(f"Unique raw results: {len(raw_results)}")
    print(f"Query errors:       {len(search_errors)}")

    print_section("4. CLOTHING RELEVANCE FILTER")
    relevant: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in raw_results:
        try:
            (relevant if cps.is_relevant_clothing(req, row) else rejected).append(row)
        except Exception as exc:
            row["filter_error"] = f"{type(exc).__name__}: {exc}"
            rejected.append(row)
    print(f"Relevant: {len(relevant)} / {len(raw_results)}")
    print(f"Rejected: {len(rejected)}")
    for row in relevant:
        print(f"[KEEP] {compact(row['title'], 120)} | {safe_domain(row['url'])}")
    for row in rejected[:10]:
        print(f"[DROP] {compact(row['title'], 120)} | {safe_domain(row['url'])}")

    print_section("5. FETCH PRODUCT PAGES / EXTRACT PRICES")
    candidates = relevant[: req.max_results * 2]
    fetched = await fetch_product_pages(candidates, max_pages=20) if candidates else []
    pages_with_prices = 0
    for row in fetched:
        info = row.get("_test_page", {})
        prices = row.get("page_prices_bdt", [])
        if prices:
            pages_with_prices += 1
        snippet_prices = cps.parse_prices(f"{row.get('title', '')} {row.get('body', '')}")
        print(f"\nTITLE: {compact(row.get('title'), 160)}")
        print(f"URL: {row.get('url')}")
        print(
            f"PAGE: status={info.get('status')} "
            f"type={info.get('content_type')} chars={info.get('html_chars')} "
            f"error={info.get('error')}"
        )
        print(f"SNIPPET PRICES: {snippet_prices}")
        print(f"PAGE PRICES:    {prices}")

    print(f"\nPages fetched: {len(fetched)} | Pages with extracted BDT price: {pages_with_prices}")

    print_section("6. REGEX EXTRACTION + VALIDATION")
    regex_items = cps.regex_extract(fetched)
    regex_offers = cps.validate(regex_items, fetched)
    print(f"Regex candidates: {len(regex_items)}")
    print(f"Validated offers: {len(regex_offers)}")
    for item in regex_items:
        print(f"[CANDIDATE] index={item.get('index')} title={item.get('product_title')} price={item.get('price_bdt')}")
    for offer in regex_offers:
        print(f"[VALID] {offer.seller} | {offer.product_title} | ৳{offer.price_bdt:,.2f} | {offer.url}")

    llm_status: dict[str, Any] = {"skipped": True, "reason": "--skip-llm used or no API key"}
    llm_items: list[dict[str, Any]] = []
    llm_offers: list[Any] = []
    api_key = getattr(cps, "OPENROUTER_API_KEY", "")

    if not args.skip_llm and api_key and fetched:
        print_section("7. OPENROUTER TEST")
        try:
            llm_items = await cps.llm_extract(req, fetched)
            llm_offers = cps.validate(llm_items, fetched)
            llm_status = {
                "ok": True,
                "returned_items": len(llm_items),
                "validated_offers": len(llm_offers),
            }
            print(f"LLM returned items: {len(llm_items)}")
            print(f"LLM validated offers: {len(llm_offers)}")
            for item in llm_items:
                print(f"[LLM ITEM] {item}")
        except Exception as exc:
            llm_status = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            print(f"OPENROUTER FAILED: {llm_status['error']}")
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                print(f"HTTP status: {exc.response.status_code}")
                print(f"Provider response: {compact(exc.response.text, 1000)}")
    else:
        print_section("7. OPENROUTER TEST")
        print("Skipped: no OPENROUTER_API_KEY_1ST key, --skip-llm was used, or no fetched candidates.")

    print_section("8. SUMMARY")
    print(f"Raw search results:       {len(raw_results)}")
    print(f"Relevant clothing pages:  {len(relevant)}")
    print(f"Pages with BDT prices:    {pages_with_prices}")
    print(f"Regex validated offers:   {len(regex_offers)}")
    print(f"LLM status:               {llm_status}")

    if not raw_results:
        diagnosis = "SEARCH: DuckDuckGo returned no results or all queries failed."
    elif not relevant:
        diagnosis = "FILTER: Search worked, but the clothing relevance filter rejected every result."
    elif not pages_with_prices and not any(cps.parse_prices(f"{r.get('title', '')} {r.get('body', '')}") for r in relevant):
        diagnosis = "PRICE DATA: Results exist, but neither snippets nor fetched pages exposed an explicit BDT price."
    elif not regex_offers and not llm_offers:
        diagnosis = "VALIDATION/EXTRACTION: Prices may have been found, but no offer survived validation. Inspect candidate and page-price output."
    else:
        diagnosis = "PIPELINE: At least one offer was extracted and validated. Compare this with the dashboard endpoint."
    print(f"\nDIAGNOSIS: {diagnosis}")

    api_test: dict[str, Any] = {"skipped": True}
    if args.api_url:
        print_section("9. RUNNING ACMS HTTP ENDPOINT TEST")
        endpoint = args.api_url.rstrip("/") + "/api/competitor-price-search"
        api_payload = {
            "product_name": req.product_name,
            "brand": req.brand,
            "category": req.category,
            "our_price": req.our_price,
            "max_results": req.max_results,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(endpoint, json=api_payload)
            api_test = {
                "url": endpoint,
                "status_code": response.status_code,
                "response": response.json() if "application/json" in response.headers.get("content-type", "") else response.text[:3000],
            }
            print(f"POST {endpoint}")
            print(f"HTTP status: {response.status_code}")
            print(json.dumps(api_test["response"], ensure_ascii=False, indent=2, default=str))
        except Exception as exc:
            api_test = {"url": endpoint, "error": f"{type(exc).__name__}: {exc}"}
            print(f"API TEST FAILED: {api_test['error']}")

    report = {
        "product": req.product_name,
        "category": req.category,
        "module_file": str(Path(cps.__file__).resolve()),
        "queries": queries,
        "search_errors": search_errors,
        "raw_results": raw_results,
        "relevant_results": relevant,
        "rejected_results": rejected,
        "regex_items": regex_items,
        "regex_offers": [o.model_dump() if hasattr(o, "model_dump") else o.dict() for o in regex_offers],
        "llm_status": llm_status,
        "llm_items": llm_items,
        "llm_offers": [o.model_dump() if hasattr(o, "model_dump") else o.dict() for o in llm_offers],
        "diagnosis": diagnosis,
        "api_test": api_test,
    }
    output_path = PROJECT_ROOT / args.output
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nFull report saved to: {output_path}")
    print("Do not share your .env file or API key. The JSON report does not include the key.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
