"""
Cloud Waste Watcher - storage (DynamoDB)

Two kinds of items share ONE table:

  pk = "SCAN#2026-10-07"   sk = "FINDING#<resource id>"
        one item per finding. Query pk = "SCAN#<date>" to get a whole day.

  pk = "SUMMARY"           sk = "2026-10-07"
        one item per scan, holding the totals. Query pk = "SUMMARY" to get
        the history of totals in date order (good for a trend chart).

Every item also carries "expires_at". Turn on DynamoDB's TTL feature for that
attribute and AWS deletes old items for free, so storage never grows forever.
"""

import time
from decimal import Decimal

from boto3.dynamodb.conditions import Key

RETENTION_DAYS = 90


def to_dynamo(value):
    """DynamoDB refuses Python floats. Turn every float into a Decimal.

    Going through str() avoids binary-float noise like 0.0912000000001.
    """
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: to_dynamo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dynamo(item) for item in value]
    return value


def save_scan(table, scan_date, region, findings, total_usd, ignored_count):
    """Write today's findings and one summary item. findings must carry
    the "monthly_usd" field (run them through pricing.with_estimates first).
    """
    expires_at = int(time.time()) + RETENTION_DAYS * 24 * 60 * 60

    # batch_writer groups writes (up to 25 per request) and retries for us.
    with table.batch_writer(overwrite_by_pkeys=["pk", "sk"]) as batch:
        for finding in findings:
            batch.put_item(
                Item=to_dynamo(
                    {
                        "pk": f"SCAN#{scan_date}",
                        "sk": f"FINDING#{finding['resource_id']}",
                        "check": finding["check"],
                        "resource_id": finding["resource_id"],
                        "title": finding["title"],
                        "age_days": finding["age_days"],
                        "tags": finding["tags"],
                        "details": finding["details"],
                        "monthly_usd": finding["monthly_usd"],
                        "region": region,
                        "expires_at": expires_at,
                    }
                )
            )

    # Same pk + sk as an earlier run today? It simply overwrites, so running
    # the scan twice in one day never creates duplicates.
    table.put_item(
        Item=to_dynamo(
            {
                "pk": "SUMMARY",
                "sk": scan_date,
                "region": region,
                "items_found": len(findings),
                "items_ignored": ignored_count,
                "estimated_monthly_usd": round(total_usd, 2),
                "expires_at": expires_at,
            }
        )
    )


def _query_all(table, **kwargs):
    """Like the paginator for EC2: keep asking until DynamoDB has no more."""
    items = []
    while True:
        response = table.query(**kwargs)
        items.extend(response["Items"])
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def get_previous_scan(table, scan_date):
    """Find the most recent scan BEFORE scan_date.

    Returns (previous_date, set_of_resource_ids), or (None, set()) if there
    is no earlier scan (for example, the very first run).
    """
    response = table.query(
        KeyConditionExpression=Key("pk").eq("SUMMARY") & Key("sk").lt(scan_date),
        ScanIndexForward=False,  # newest first
        Limit=1,
    )
    if not response["Items"]:
        return None, set()

    previous_date = response["Items"][0]["sk"]
    items = _query_all(
        table, KeyConditionExpression=Key("pk").eq(f"SCAN#{previous_date}")
    )
    return previous_date, {item["resource_id"] for item in items}
