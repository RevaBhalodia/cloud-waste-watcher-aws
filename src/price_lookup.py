"""
Look up Mumbai prices from the AWS Price List API (free to call).

Usage (from the project folder, with the virtual environment active):
    python price_lookup.py gp3         # an EBS volume type
    python price_lookup.py gp2
    python price_lookup.py snapshot    # EBS snapshot storage

It prints each matching price with its "usagetype" and description, so you
can pick the right one and copy the number into pricing.py.
"""

import json
import sys

import boto3

PRICING_API_REGION = "us-east-1"  # the Price List API lives here
PRICE_REGION = "ap-south-1"       # the region whose prices we want (Mumbai)


def build_filters(kind):
    filters = [{"Type": "TERM_MATCH", "Field": "regionCode", "Value": PRICE_REGION}]
    if kind == "snapshot":
        filters.append(
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage Snapshot"}
        )
    else:
        filters.append({"Type": "TERM_MATCH", "Field": "volumeApiName", "Value": kind})
        filters.append(
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Storage"}
        )
    return filters


def parse_price_item(raw):
    """One entry in PriceList is a JSON *string* (JSON inside JSON), so we
    must json.loads() it before we can dig into it.

    The price hides under: terms -> OnDemand -> <offer id> -> priceDimensions
    -> <rate id> -> pricePerUnit -> USD. The ids change, so we loop over
    .values() instead of hard-coding them.
    """
    item = json.loads(raw)
    usagetype = item["product"]["attributes"].get("usagetype")

    results = []
    for term in item["terms"]["OnDemand"].values():
        for dimension in term["priceDimensions"].values():
            results.append(
                {
                    "usagetype": usagetype,
                    "unit": dimension["unit"],
                    "description": dimension["description"],
                    "usd": float(dimension["pricePerUnit"]["USD"]),
                }
            )
    return results


def lookup(pricing_client, kind):
    paginator = pricing_client.get_paginator("get_products")
    pages = paginator.paginate(ServiceCode="AmazonEC2", Filters=build_filters(kind))

    results = []
    for page in pages:
        for raw in page["PriceList"]:
            results.extend(parse_price_item(raw))
    return results


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return

    kind = sys.argv[1]
    client = boto3.client("pricing", region_name=PRICING_API_REGION)
    results = lookup(client, kind)

    if not results:
        print(f"No prices found for '{kind}' in {PRICE_REGION}.")
        return

    for r in results:
        print(f"{r['usagetype']}")
        print(f"    ${r['usd']} per {r['unit']}")
        print(f"    {r['description']}\n")


if __name__ == "__main__":
    main()
