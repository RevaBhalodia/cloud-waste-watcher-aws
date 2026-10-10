"""
Cloud Waste Watcher - Lambda entry point

AWS Lambda calls lambda_handler() each time the schedule fires.

Pipeline: scan -> ignore list -> prices -> compare with the previous scan
          -> save to DynamoDB -> email the digest through SNS.

Settings come from Lambda ENVIRONMENT VARIABLES, not from the code:
  TABLE_NAME   DynamoDB table to save into   (skip saving if not set)
  TOPIC_ARN    SNS topic to email through    (skip the email if not set)
  SCAN_REGION  region to scan                (default: the Lambda's region)

READ-ONLY toward your resources: it advises, it never deletes.
"""

import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

import digest
import pricing
import scan
import storage


def lambda_handler(event, context):
    region = os.environ.get("SCAN_REGION") or os.environ.get("AWS_REGION") or scan.REGION
    table_name = os.environ.get("TABLE_NAME")
    topic_arn = os.environ.get("TOPIC_ARN")

    # 1. Detect, filter, price: the same pipeline as on your laptop.
    ec2 = boto3.client("ec2", region_name=region)
    findings, errors = scan.run_all_checks(ec2)
    kept, ignored = scan.apply_ignore_list(findings)
    estimated = pricing.with_estimates(kept)
    total = sum(f["monthly_usd"] for f in estimated if f["monthly_usd"] is not None)

    scan_date = datetime.now(timezone.utc).date().isoformat()

    # 2. Compare with the previous scan, then save today's. A storage problem
    #    must not stop the email, so it is recorded as an error and we go on.
    previous_date, new_ids, saved = None, None, False
    if table_name:
        try:
            table = boto3.resource("dynamodb", region_name=region).Table(table_name)
            previous_date, previous_ids = storage.get_previous_scan(table, scan_date)
            if previous_date is not None:
                new_ids = {f["resource_id"] for f in estimated} - previous_ids
            storage.save_scan(table, scan_date, region, estimated, total, len(ignored))
            saved = True
        except ClientError as err:
            errors.append(f"save_to_dynamodb: {err.response['Error']['Code']}")

    # 3. Build the digest and email it.
    subject, body = digest.build_digest(
        estimated, new_ids, len(ignored), errors, region, scan_date, previous_date
    )
    digest_sent = False
    if topic_arn:
        try:
            sns = boto3.client("sns", region_name=topic_arn.split(":")[3])
            digest.send_digest(sns, topic_arn, subject, body)
            digest_sent = True
        except ClientError as err:
            errors.append(f"send_digest: {err.response['Error']['Code']}")

    # print() output goes to CloudWatch Logs.
    scan.print_report(estimated, len(ignored), errors)

    return {
        "region": region,
        "scan_date": scan_date,
        "items_found": len(estimated),
        "items_new": None if new_ids is None else len(new_ids),
        "items_ignored": len(ignored),
        "estimated_monthly_usd": round(total, 2),
        "saved_to_dynamodb": saved,
        "digest_sent": digest_sent,
        "errors": errors,
    }
