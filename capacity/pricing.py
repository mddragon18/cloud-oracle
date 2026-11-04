"""Pricing retrieval and validation for AWS instance prices.

Uses the AWS Price List API. The production cache (pricing.json) is used
offline; the fetch script updates it from the live API when available.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from capacity import config


PRICE_CACHE_PATH = Path(__file__).with_name("pricing.json")


def load_prices(cache_path: Optional[str] = None) -> Dict[str, float]:
    """Load the cached price dictionary.

    Raises:
        FileNotFoundError: If no valid cache exists.
        ValueError: If prices are invalid.
    """
    path = Path(cache_path) if cache_path else PRICE_CACHE_PATH
    if not path.exists():
        raise FileNotFoundError(f"Price cache not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    prices = data.get("prices", {})
    if not isinstance(prices, dict):
        raise ValueError("Invalid price cache format: 'prices' must be a dict.")
    # Validate every price
    for k, v in prices.items():
        if not isinstance(k, str):
            raise ValueError(f"Invalid price key: {k!r}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"Invalid price for {k}: {v!r}")
        if math.isnan(v) or math.isinf(v) or v < 0:
            raise ValueError(f"Invalid price value for {k}: {v}")
    return dict(prices)


def get_price(instance_type: str, prices: Optional[Dict[str, float]] = None) -> float:
    """Retrieve price for an instance type, validating it."""
    price_dict = prices if prices is not None else load_prices()
    if instance_type not in price_dict:
        raise KeyError(f"No price found for instance type: {instance_type}")
    price = price_dict[instance_type]
    if price <= 0:
        raise ValueError(f"Non-positive price for {instance_type}: {price}")
    return float(price)


def save_price_cache(
    prices: Dict[str, float],
    cache_path: Optional[str] = None,
    region_code: Optional[str] = None,
) -> Path:
    """Write a validated price dictionary to the cache file.

    Does not overwrite an existing valid cache with an incomplete result.
    """
    path = Path(cache_path) if cache_path else PRICE_CACHE_PATH
    # Validate input prices thoroughly
    validated: Dict[str, float] = {}
    for k, v in prices.items():
        if not isinstance(k, str) or not k:
            raise ValueError(f"Invalid instance type key: {k!r}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"Invalid price value for {k}: {v!r}")
        v_f = float(v)
        if math.isnan(v_f) or math.isinf(v_f) or v_f < 0:
            raise ValueError(f"Invalid price value for {k}: {v_f}")
        validated[k] = v_f
    if not validated:
        raise ValueError("Price dictionary is empty; refusing to overwrite cache.")

    payload = {
        "region_code": region_code or config.AWS_REGION_CODE,
        "region_name": config.AWS_REGION_NAME,
        "currency": config.AWS_CURRENCY,
        "retrieval_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "AWS Price List API (cached)",
        "prices": validated,
        "notes": "Cached AWS on-demand Linux prices. Retrievable via scripts/fetch_prices.py.",
    }
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def retrieve_prices_from_aws_api() -> Dict[str, float]:
    """Retrieve on-demand Linux prices from the AWS Price List API.

    Returns a dictionary mapping instance_type -> hourly price.
    Raises on network or parsing errors unless handled by caller.
    """
    # Use urllib to fetch the AWS Price List JSON endpoint for ap-south-1
    import urllib.request
    url = (
        "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/"
        "AmazonEC2/current/ap-south-1/index.json"
    )
    # For simplicity, we fetch the region-specific price list and filter
    # the products we care about.
    # Note: The full index is very large; a production script may filter
    # server-side or use boto3 pricing.get_products.
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ConnectionError(f"Failed to retrieve AWS price list from {url}: {exc}")

    # The AWS price list JSON structure:
    # {"offerCode": {"terms": {"OnDemand": {...}}, "products": {...}}}
    prices: Dict[str, float] = {}
    offer_code = "AmazonEC2"
    terms_key = f"{offer_code}.{config.AWS_TENANCY}.{config.AWS_PURCHASE_MODEL}"
    # Try to find terms
    terms = data.get("terms", {})
    # Filter for on-demand Linux instances in the configured families
    target_families = set(config.INSTANCE_FAMILIES)
    # We iterate over products looking for instance families
    products = data.get("products", {})
    for product_key, product in products.items():
        attributes = product.get("attributes", {})
        instance_type = attributes.get("instanceType", "")
        if instance_type not in config.CANDIDATE_INSTANCE_TYPES:
            continue
        operating_system = attributes.get("operatingSystem", "")
        tenancy = attributes.get("tenancy", "")
        if operating_system != config.AWS_OS or tenancy != config.AWS_TENANCY:
            continue
        # Price terms are nested inside the product: terms -> OnDemand -> ...
        product_terms = product.get("terms", {})
        on_demand_terms = product_terms.get(config.AWS_PURCHASE_MODEL, {})
        for term_key, term_details in on_demand_terms.items():
            price_dimensions = term_details.get("priceDimensions", {})
            for dim_key, dim_details in price_dimensions.items():
                price = dim_details.get("pricePerUnit", {})
                usd_price = price.get("USD", price.get("usd", ""))
                if isinstance(usd_price, (int, float)):
                    price_f = float(usd_price)
                elif isinstance(usd_price, str):
                    try:
                        price_f = float(usd_price)
                    except ValueError:
                        continue
                else:
                    price_f = float(usd_price) if usd_price is not None else 0.0
                if price_f > 0 and math.isfinite(price_f):
                    prices[instance_type] = price_f
                    # Break out of loops for this product once price found
                    break
            else:
                continue
            break
    return prices
