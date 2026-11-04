#!/usr/bin/env python3
"""Retrieve AWS Price List prices and update capacity/pricing.json.

Requires internet access. Uses urllib and does not require boto3.
Handles failures gracefully: does not overwrite an existing valid cache
with an incomplete result.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capacity import pricing, config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch AWS Price List on-demand Linux prices for ap-south-1 and update pricing.json"
    )
    parser.add_argument(
        "--region",
        default=config.AWS_REGION_CODE,
        help="AWS region code (default: ap-south-1)",
    )
    args = parser.parse_args()

    print(f"Fetching AWS Price List for region: {args.region}")
    try:
        prices = pricing.retrieve_prices_from_aws_api()
    except Exception as exc:
        print(f"ERROR: Price retrieval failed: {exc}")
        print("The existing pricing.json will NOT be overwritten.")
        return 1

    if not prices:
        print("ERROR: Price retrieval returned empty results.")
        print("The existing pricing.json will NOT be overwritten.")
        return 1

    # Validate all prices
    valid_prices = {}
    for k, v in prices.items():
        import math
        if not isinstance(k, str) or not k:
            print(f"WARNING: Skipping invalid key: {k!r}")
            continue
        try:
            v_f = float(v)
        except (TypeError, ValueError):
            print(f"WARNING: Skipping invalid price for {k}: {v!r}")
            continue
        if math.isnan(v_f) or math.isinf(v_f) or v_f < 0:
            print(f"WARNING: Skipping non-positive/non-finite price for {k}: {v_f}")
            continue
        valid_prices[k] = v_f

    if not valid_prices:
        print("ERROR: No valid prices after filtering.")
        return 1

    # Save only if we have valid prices
    saved_path = pricing.save_price_cache(valid_prices, region_code=args.region)
    print(f"Saved {len(valid_prices)} prices to {saved_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
