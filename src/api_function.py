"""
Cloud Waste Watcher - dashboard API (Lambda behind a Function URL)

Read-only. Returns the last 30 daily summaries plus the latest scan's findings.
Protected by a shared secret: the dashboard sends  Authorization: Bearer <token>.
Env vars: TABLE_NAME, DASHBOARD_TOKEN
"""
import hmac
import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key


def _default(value):
    if isinstance(value, Decimal):  # DynamoDB gives Decimal; JSON wants numbers
        return float(value)
    raise TypeError(type(value))


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, default=_default),
    }


def lambda_handler(event, context):
    sent = (event.get("headers") or {}).get("authorization", "")
    expected = "Bearer " + os.environ["DASHBOARD_TOKEN"]
    # compare_digest takes the same time however many characters match
    if not hmac.compare_digest(sent.encode(), expected.encode()):
        return _reply(401, {"error": "unauthorized"})

    table = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION")).Table(os.environ["TABLE_NAME"])
    rows = table.query(
        KeyConditionExpression=Key("pk").eq("SUMMARY"),
        ScanIndexForward=False,  # newest first
        Limit=30,
    )["Items"]
    if not rows:
        return _reply(200, {"scan_date": None, "history": [], "findings": []})

    latest = rows[0]["sk"]
    items = table.query(KeyConditionExpression=Key("pk").eq(f"SCAN#{latest}"))["Items"]
    return _reply(200, {
        "scan_date": latest,
        "history": [{"date": r["sk"], "total": r["estimated_monthly_usd"],
                     "items": r["items_found"]} for r in reversed(rows)],
        "findings": [{k: i.get(k) for k in
                      ("check", "resource_id", "title", "age_days", "monthly_usd", "tags")}
                     for i in items],
    })
